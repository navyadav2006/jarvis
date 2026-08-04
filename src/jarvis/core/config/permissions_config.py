"""permissions.yaml — which plugins may use which capability scopes
(filesystem, automation, network, ...).

Modeled and validated now; not yet *enforced* anywhere — no code in
orchestrator/ or a future AutomationPort implementation calls
`is_allowed()` yet. It's defined here, in the config system, rather
than deferred to whichever phase adds enforcement, because the schema
for an allow/deny rule set isn't actually complete without also fixing
its precedence semantics (does deny beat allow? does an exact
plugin-name rule beat a wildcard rule?) — and those semantics belong
with the data they govern, not scattered into whatever calls
`is_allowed()` later. See docs/architecture.md's Phase 3 section for
the full rationale and what a future enforcement point would look like.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PERMISSIONS_FILENAME = "permissions.yaml"


class PermissionRule(BaseModel):
    """One rule: what `plugin` (or `"*"` for every plugin) may/may not do."""

    model_config = ConfigDict(frozen=True)

    plugin: str = Field(..., description="Plugin name, or '*' to match every plugin.")
    allow: list[str] = Field(
        default_factory=list, description="Capability scopes explicitly allowed."
    )
    deny: list[str] = Field(
        default_factory=list, description="Capability scopes explicitly denied."
    )

    @field_validator("plugin")
    @classmethod
    def _plugin_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("plugin must not be blank")
        return value


class PermissionsConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    default_policy: Literal["allow", "deny"] = Field(
        "deny", description="Outcome when no rule matches a scope."
    )
    rules: list[PermissionRule] = Field(default_factory=list)

    def is_allowed(self, plugin: str, scope: str) -> bool:
        """Precedence: an exact plugin-name rule beats a '*' wildcard rule;
        within a rule, deny beats allow; if nothing matches at all,
        default_policy decides. Deny-by-default unless configured otherwise.
        """
        for rule in self._matching_rules(plugin):
            if scope in rule.deny:
                return False
            if scope in rule.allow:
                return True
        return self.default_policy == "allow"

    def _matching_rules(self, plugin: str) -> list[PermissionRule]:
        exact = [rule for rule in self.rules if rule.plugin == plugin]
        wildcard = [rule for rule in self.rules if rule.plugin == "*"]
        return exact + wildcard
