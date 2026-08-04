from __future__ import annotations

from jarvis.core.vault.backlinks import add_backlink, extract_links


def test_extract_links_finds_wikilinks() -> None:
    assert extract_links("See [[Foo]] and [[Bar]].") == ["Foo", "Bar"]


def test_extract_links_dedupes() -> None:
    assert extract_links("[[Foo]] again [[Foo]]") == ["Foo"]


def test_extract_links_strips_alias_and_heading_suffixes() -> None:
    assert extract_links("[[Foo|display text]] and [[Bar#Section]]") == ["Foo", "Bar"]


def test_extract_links_ignores_generated_backlinks_section() -> None:
    body = "Real content [[Alpha]]\n\n## Backlinks\n- [[Beta]]\n"
    assert extract_links(body) == ["Alpha"]


def test_add_backlink_creates_section_when_absent() -> None:
    result = add_backlink("some content", from_note="Foo")
    assert result == "some content\n\n## Backlinks\n- [[Foo]]\n"


def test_add_backlink_appends_to_existing_section() -> None:
    body = "content\n\n## Backlinks\n- [[Alpha]]\n"
    result = add_backlink(body, from_note="Beta")
    assert "- [[Alpha]]" in result
    assert "- [[Beta]]" in result


def test_add_backlink_is_idempotent() -> None:
    body = "content\n\n## Backlinks\n- [[Foo]]\n"
    result = add_backlink(body, from_note="Foo")
    assert result == body
    assert result.count("[[Foo]]") == 1
