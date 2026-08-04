"""Maps each `(category, action)` ExecutionEngine already knows about
(Phase 15's filesystem/terminal/desktop/application/clipboard/
screenshot/window, Phase 16's browser) onto one of the six
PermissionLevels, and separately onto a `permissions.yaml` scope
string.

`PERMISSION_SCOPES` used to be a private `_SCOPES` dict inside
`core/execution/engine.py`; it now lives here, and `ExecutionEngine`
imports it from this module. The two use the exact same table
specifically so SecurityManager and ExecutionEngine agree on what
scope string a given `(category, action)` maps to — a real bug in this
phase's first draft had SecurityManager compute `f"{category}.{action}"`
directly (e.g. `"clipboard.get"`) while ExecutionEngine looked up its
own separately-defined `"clipboard.read"`, so a `permissions.yaml` rule
written for one silently didn't unlock the other. Caught by running
the two together, not by reading either in isolation.

Anything NOT in `LEVELS` maps to `BLOCKED` — deny-by-default, the same
posture `PermissionsConfig.default_policy` and
`FilesystemConfig.allowed_dirs` both take. A new action Phase 15/16
never anticipated must be classified here explicitly before
SecurityManager will ever let it through, rather than silently
defaulting to something permissive.
"""

from __future__ import annotations

from jarvis.core.security.types import PermissionLevel

# category, action -> permission scope. Chosen to match the scope names
# config/examples/permissions.example.yaml already anticipated
# (automation.mouse/automation.keyboard) rather than inventing new ones.
# The single source of truth for this mapping — see the module
# docstring for why it isn't duplicated in core/execution/engine.py.
PERMISSION_SCOPES: dict[tuple[str, str], str] = {
    ("filesystem", "read"): "filesystem.read",
    ("filesystem", "search"): "filesystem.read",
    ("filesystem", "write"): "filesystem.write",
    ("filesystem", "copy"): "filesystem.write",
    ("filesystem", "move"): "filesystem.write",
    ("filesystem", "rename"): "filesystem.write",
    ("filesystem", "delete"): "filesystem.write",
    ("terminal", "run"): "terminal.run",
    ("desktop", "click"): "automation.mouse",
    ("desktop", "type_text"): "automation.keyboard",
    ("desktop", "key_press"): "automation.keyboard",
    ("application", "launch"): "application.launch",
    ("application", "close"): "application.close",
    ("clipboard", "get"): "clipboard.read",
    ("clipboard", "set"): "clipboard.write",
    ("screenshot", "capture"): "screenshot.capture",
    ("window", "list"): "window.read",
    ("window", "focus"): "window.write",
    ("window", "minimize"): "window.write",
    ("window", "maximize"): "window.write",
    ("browser", "search"): "browser.control",
    ("browser", "navigate"): "browser.control",
    ("browser", "fill_form"): "browser.control",
    ("browser", "authenticate"): "browser.control",
    ("browser", "download"): "browser.control",
    ("browser", "screenshot"): "browser.control",
    ("browser", "summarize_page"): "browser.control",
}


def scope_for(category: str, action: str) -> str | None:
    return PERMISSION_SCOPES.get((category, action))

LEVELS: dict[tuple[str, str], PermissionLevel] = {
    ("filesystem", "read"): PermissionLevel.READ,
    ("filesystem", "search"): PermissionLevel.READ,
    ("filesystem", "write"): PermissionLevel.WRITE,
    ("filesystem", "copy"): PermissionLevel.WRITE,
    ("filesystem", "move"): PermissionLevel.WRITE,
    ("filesystem", "rename"): PermissionLevel.WRITE,
    ("filesystem", "delete"): PermissionLevel.DANGEROUS,
    ("terminal", "run"): PermissionLevel.EXECUTE,
    ("desktop", "click"): PermissionLevel.EXECUTE,
    ("desktop", "type_text"): PermissionLevel.EXECUTE,
    ("desktop", "key_press"): PermissionLevel.EXECUTE,
    ("application", "launch"): PermissionLevel.EXECUTE,
    ("application", "close"): PermissionLevel.DANGEROUS,
    ("clipboard", "get"): PermissionLevel.READ,
    ("clipboard", "set"): PermissionLevel.WRITE,
    ("screenshot", "capture"): PermissionLevel.READ,
    ("window", "list"): PermissionLevel.READ,
    ("window", "focus"): PermissionLevel.EXECUTE,
    ("window", "minimize"): PermissionLevel.EXECUTE,
    ("window", "maximize"): PermissionLevel.EXECUTE,
    ("browser", "search"): PermissionLevel.READ,
    ("browser", "summarize_page"): PermissionLevel.READ,
    ("browser", "navigate"): PermissionLevel.EXECUTE,
    ("browser", "fill_form"): PermissionLevel.EXECUTE,
    ("browser", "screenshot"): PermissionLevel.EXECUTE,
    ("browser", "download"): PermissionLevel.EXECUTE,
    ("browser", "authenticate"): PermissionLevel.DANGEROUS,
    # Plugin-framework and security-manager-owned actions (Phase 18/19)
    # — not part of ExecutionEngine's dispatch table, but still need a
    # level so a caller can route them through the same gate.
    ("plugin", "install"): PermissionLevel.ADMINISTRATOR,
    ("security", "emergency_shutdown"): PermissionLevel.ADMINISTRATOR,
    ("security", "resume"): PermissionLevel.ADMINISTRATOR,
}


def level_for(category: str, action: str) -> PermissionLevel:
    return LEVELS.get((category, action), PermissionLevel.BLOCKED)
