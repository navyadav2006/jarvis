"""Automatic backlinks: `[[Note Name]]`-style wikilink extraction and
the "## Backlinks" section VaultService appends to a linked note.

Kept as pure functions over strings — no filesystem access here, so
they're trivially unit-testable and service.py stays the only place
that decides when to call them.
"""

from __future__ import annotations

import re

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
BACKLINKS_HEADING = "## Backlinks"


def extract_links(body: str) -> list[str]:
    """Every `[[Target]]` (or `[[Target|alias]]`, `[[Target#heading]]`)
    referenced in `body`'s *authored* content, in order, without
    duplicates. Stops at the "## Backlinks" section (if any): those
    entries are generated metadata, not authored links, and treating
    them as outgoing links would make add_backlink()'s own output
    trigger further backlink propagation back the other way.
    """
    authored = body.split(BACKLINKS_HEADING, 1)[0]
    seen: dict[str, None] = {}
    for match in _WIKILINK_RE.finditer(authored):
        target = match.group(1).strip()
        if target:
            seen.setdefault(target, None)
    return list(seen)


def add_backlink(body: str, *, from_note: str) -> str:
    """Append `from_note` to `body`'s "## Backlinks" section, creating
    the section if needed. Idempotent — calling it again with the same
    `from_note` doesn't duplicate the entry.
    """
    entry = f"- [[{from_note}]]"
    if BACKLINKS_HEADING not in body:
        stripped = body.rstrip("\n")
        separator = "\n\n" if stripped else ""
        return f"{stripped}{separator}{BACKLINKS_HEADING}\n{entry}\n"

    lines = body.splitlines()
    heading_index = next(i for i, line in enumerate(lines) if line.strip() == BACKLINKS_HEADING)
    existing_entries = []
    end = len(lines)
    for i in range(heading_index + 1, len(lines)):
        if lines[i].startswith("- "):
            existing_entries.append(lines[i])
        elif lines[i].strip() == "":
            continue
        else:
            end = i
            break

    if entry in existing_entries:
        return body  # already linked — nothing to do

    new_lines = lines[: heading_index + 1] + existing_entries + [entry] + lines[end:]
    return "\n".join(new_lines) + ("\n" if body.endswith("\n") else "")
