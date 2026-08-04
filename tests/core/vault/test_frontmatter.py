from __future__ import annotations

from jarvis.core.vault.frontmatter import parse_frontmatter, render_frontmatter


def test_parse_returns_empty_dict_for_plain_text() -> None:
    fm, body = parse_frontmatter("just a note, no frontmatter")
    assert fm == {}
    assert body == "just a note, no frontmatter"


def test_render_then_parse_round_trips() -> None:
    fm = {"title": "Foo", "tags": ["a", "b"], "created": "2026-01-01"}
    text = render_frontmatter(fm, "the body")
    parsed_fm, parsed_body = parse_frontmatter(text)
    assert parsed_fm == fm
    assert parsed_body == "the body"


def test_render_with_empty_frontmatter_returns_plain_body() -> None:
    assert render_frontmatter({}, "just body") == "just body"


def test_parse_unclosed_delimiter_treated_as_plain_body() -> None:
    text = "---\ntitle: Foo\nno closing delimiter here"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == text


def test_parse_non_mapping_yaml_treated_as_plain_body() -> None:
    text = "---\n- just\n- a\n- list\n---\nbody"
    fm, body = parse_frontmatter(text)
    assert fm == {}
    assert body == text
