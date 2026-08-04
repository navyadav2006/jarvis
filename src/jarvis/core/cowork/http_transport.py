"""HttpCoworkTransport: the one real CoworkTransport implementation —
calls the actual Claude API (`POST /v1/messages`, via the official
`anthropic` Python SDK), not a fictional "Claude Cowork" HTTP product.

CORRECTION: the original implementation of this class POSTed to a
fabricated `https://api.anthropic.com/cowork/v1/tasks` endpoint with an
`Authorization: Bearer` header, over raw `httpx` — a shape invented
before Cowork's real API contract was verified, flagged at the time as
"implemented against a generic bearer-token REST-JSON shape... verify
against Cowork's actual API docs before enabling this in production."
That verification never happened because there is no such product: no
"Claude Cowork" HTTP API exists. The only real API is the Claude
Messages API (`POST /v1/messages`, `x-api-key` header, `anthropic-
version` header). This class now calls that, via the official
`anthropic` SDK — never raw HTTP, per Anthropic's own guidance for
languages with an official SDK.

Cowork's plan-of-steps contract (`CoworkTaskResponse`/`CoworkPlanStep`,
core/cowork/models.py) is produced via Claude's structured outputs
(`output_config.format` with a JSON Schema), not free-text parsing —
this forces the model to a fixed shape Jarvis validates against those
same pydantic models via `CoworkClient._parse_response()` (unchanged).
A step's automation parameters travel as a JSON-encoded *string* field
(`automation_parameters_json`) rather than an open `dict[str, Any]`,
since structured-outputs schemas require `additionalProperties: false`
throughout and a genuinely free-form params object can't satisfy that;
this transport parses that string back into a real dict before
returning, so `CoworkPlanStep.automation.parameters` still ends up a
plain dict exactly as `AutomationActionModel` expects.

`anthropic` is imported lazily inside `_ensure_client()`, matching
every other optional third-party dependency in this project —
constructing this class, and importing jarvis.core.cowork generally,
never requires it to be installed.

`CoworkClient` (client.py) needed zero changes: this class still
implements `CoworkTransport.post_json(path, payload, timeout=...)`.
`path` is accepted but unused — there's no dotted sub-endpoint on the
real Messages API to route by — and `payload` is still exactly the
`CoworkTaskRequest.model_dump(mode="json")` shape CoworkClient already
builds. Everything above CoworkClient (retry, backoff, diagnostics,
NullCoworkClientPort, CoworkWorkspace) is unaffected.

NOTE: like every other real backend in this project, the exact
`output_config.format` / structured-outputs request shape here was
implemented against documented behavior, not verified against a live
API call in this environment. Send one real request after enabling
and inspect the response before relying on this in production.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from jarvis.core.config.cowork_config import CoworkConfig
from jarvis.core.exceptions import CoworkUnavailableError

logger = logging.getLogger(__name__)

# Mirrors core/security/levels.py's PERMISSION_SCOPES table — the exact
# (category, action) pairs ExecutionEngine (core/execution/engine.py)
# knows how to run. Told to the model as plain text (not enforced by
# this module) so it proposes actions Jarvis can actually execute;
# SecurityManager/ExecutionEngine are the real enforcement point either
# way, so a hallucinated action name just fails harmlessly when run.
_AUTOMATION_CATALOG = """\
Available automation actions (category.action -> parameters):
  filesystem.read(path)
  filesystem.write(path, content, confirmed)
  filesystem.copy(source, destination, confirmed)
  filesystem.move(source, destination, confirmed)
  filesystem.rename(path, new_name, confirmed)
  filesystem.delete(path, confirmed)
  filesystem.search(directory, pattern, recursive)
  terminal.run(command, args, timeout)
  desktop.click(x, y)
  desktop.type_text(text)
  desktop.key_press(key)
  application.launch(path, args)
  application.close(process_name)
  clipboard.get()
  clipboard.set(text)
  screenshot.capture(path)
  window.list()
  window.focus(title)
  window.minimize(title)
  window.maximize(title)
  browser.search(query)
  browser.navigate(url)
  browser.fill_form(fields, submit)
  browser.download(url, path)
  browser.screenshot(path)
  browser.summarize_page(url)
Use only these action names — anything else is rejected before it can
run. `confirmed` gates destructive filesystem operations; set it true
only when the user's instruction was unambiguous about wanting that.
"""

_DEFAULT_SYSTEM_PROMPT = (
    "You are Jarvis's Cowork collaborator: a desktop assistant that turns one "
    "spoken or typed instruction into a short plan of steps Jarvis executes "
    "locally. Prefer a single 'respond' step for anything that's just an answer "
    "(no OS action needed). Use 'automation' steps only for real actions from "
    "the catalog below, in the order they should run.\n\n" + _AUTOMATION_CATALOG
)

# Structured-outputs JSON Schema for CoworkTaskResponse's wire shape
# (minus `task_id`, which the transport fills in from the request
# rather than trusting the model to echo it correctly). See the module
# docstring for why `automation_parameters_json` is a string, not a
# nested object.
_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One or two sentences summarizing the plan or the direct answer.",
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "integer"},
                    "description": {"type": "string"},
                    "action_type": {"type": "string", "enum": ["automation", "respond"]},
                    "automation_name": {
                        "type": "string",
                        "description": (
                            "A dotted 'category.action' name from the automation catalog. "
                            "Empty string when action_type is 'respond'."
                        ),
                    },
                    "automation_parameters_json": {
                        "type": "string",
                        "description": (
                            "JSON-encoded object of parameters for automation_name, e.g. "
                            '\'{"path": "C:/notes.txt"}\'. \'{}\' when action_type is '
                            "'respond' or the action takes no parameters."
                        ),
                    },
                    "response_text": {
                        "type": "string",
                        "description": (
                            "Text to speak/show the user for this step. Empty string when "
                            "action_type is 'automation'."
                        ),
                    },
                },
                "required": [
                    "step_id",
                    "description",
                    "action_type",
                    "automation_name",
                    "automation_parameters_json",
                    "response_text",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "steps"],
    "additionalProperties": False,
}


class HttpCoworkTransport:
    """Implements core.cowork.ports.CoworkTransport."""

    def __init__(self, config: CoworkConfig) -> None:
        self._config = config
        self._client: Any = None

    def post_json(self, path: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        client = self._ensure_client()
        import anthropic

        system_prompt = _DEFAULT_SYSTEM_PROMPT
        context = payload.get("context") or {}
        if context:
            system_prompt += f"\n\nRelevant context:\n{json.dumps(context, indent=2)}"

        try:
            response = client.with_options(timeout=timeout).messages.create(
                model=self._config.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": payload.get("instruction", "")}],
                output_config={"format": {"type": "json_schema", "schema": _RESPONSE_SCHEMA}},
            )
        except anthropic.APITimeoutError as exc:
            raise TimeoutError(str(exc)) from exc

        return self._to_response_dict(payload["task_id"], response)

    def _to_response_dict(self, task_id: str, response: Any) -> dict[str, Any]:
        if response.stop_reason == "refusal":
            logger.warning("Cowork request %s was refused by Claude's safety classifiers", task_id)
            return {
                "task_id": task_id,
                "summary": "Claude declined this request.",
                "steps": [],
                "raw": {"stop_reason": "refusal"},
            }

        text = next(block.text for block in response.content if block.type == "text")
        parsed = json.loads(text)

        steps = []
        for step in parsed.get("steps", []):
            action_type = step["action_type"]
            automation = None
            response_text = None
            if action_type == "automation":
                automation = {
                    "name": step["automation_name"],
                    "parameters": json.loads(step["automation_parameters_json"] or "{}"),
                }
            else:
                response_text = step["response_text"]
            steps.append(
                {
                    "step_id": step["step_id"],
                    "description": step["description"],
                    "action_type": action_type,
                    "automation": automation,
                    "response_text": response_text,
                }
            )

        return {"task_id": task_id, "summary": parsed["summary"], "steps": steps, "raw": parsed}

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client

        try:
            import anthropic
        except ImportError as exc:
            raise CoworkUnavailableError(
                "the 'anthropic' package is not installed; install the 'cowork' extra "
                "(pip install -e '.[cowork]') to use HttpCoworkTransport"
            ) from exc

        api_key = os.environ.get(self._config.api_key_env_var)
        if not api_key:
            raise CoworkUnavailableError(
                f"environment variable {self._config.api_key_env_var} is not set "
                "(update cowork.yaml's api_key_env_var, or set it in the environment)"
            )

        logger.info("Creating Anthropic client for Cowork (model=%s)", self._config.model)
        self._client = anthropic.Anthropic(api_key=api_key)
        return self._client
