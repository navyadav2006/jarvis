"""YAML frontmatter parsing/rendering for vault notes.

Uses PyYAML, already a base dependency (see requirements.txt) — no new
dependency for this phase. Frontmatter is the `---`-delimited block
Obsidian (and most static-site tools) put at the top of a Markdown
file; everything after it is the note body.
"""

from __future__ import annotations

from typing import Any

import yaml

_DELIMITER = "---"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split `text` into (frontmatter dict, body). A note with no
    frontmatter block returns an empty dict and the text unchanged.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != _DELIMITER:
        return {}, text

    for i in range(1, len(lines)):
        if lines[i].strip() == _DELIMITER:
            raw = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :]).lstrip("\n")
            parsed = yaml.safe_load(raw) or {}
            if not isinstance(parsed, dict):
                return {}, text
            return parsed, body

    return {}, text  # opening delimiter with no closing one — treat as plain body


def render_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    """The inverse of parse_frontmatter(). An empty frontmatter dict
    renders no block at all, so a plain note round-trips as plain text.
    """
    if not frontmatter:
        return body
    yaml_block = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{_DELIMITER}\n{yaml_block}\n{_DELIMITER}\n\n{body}"
