from __future__ import annotations

from jarvis.core.planning.decomposition import decompose_request


def test_empty_request_returns_no_tasks() -> None:
    assert decompose_request("") == []
    assert decompose_request("   ") == []


def test_single_sentence_stays_one_task() -> None:
    assert decompose_request("turn on the lights") == ["turn on the lights"]


def test_semicolon_separated_splits_into_multiple_tasks() -> None:
    result = decompose_request("research pricing; write a summary")
    assert result == ["research pricing", "write a summary"]


def test_then_separated_splits_into_multiple_tasks() -> None:
    result = decompose_request("open the file then edit it then save it")
    assert result == ["open the file", "edit it", "save it"]


def test_numbered_list_splits_into_tasks() -> None:
    request = "1. research pricing\n2. write a summary\n3. send it"
    result = decompose_request(request)
    assert result == ["research pricing", "write a summary", "send it"]


def test_bulleted_list_splits_into_tasks() -> None:
    request = "- research pricing\n- write a summary"
    result = decompose_request(request)
    assert result == ["research pricing", "write a summary"]
