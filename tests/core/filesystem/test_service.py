from __future__ import annotations

import logging
from pathlib import Path

import pytest

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.events import EventBus
from jarvis.core.exceptions import (
    ConfirmationRequiredError,
    FilesystemAccessError,
    FilesystemOperationError,
)
from jarvis.core.filesystem.service import LocalFilesystemService

# -- read / write -------------------------------------------------------------


def test_write_then_read_round_trips(service: LocalFilesystemService, allowed_dir: Path) -> None:
    target = allowed_dir / "note.txt"
    service.write(target, "hello world")
    assert service.read(target) == "hello world"


def test_write_creates_parent_directories(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    target = allowed_dir / "sub" / "dir" / "note.txt"
    service.write(target, "nested")
    assert target.read_text(encoding="utf-8") == "nested"


def test_read_denied_outside_allowed_dir(service: LocalFilesystemService, root: Path) -> None:
    with pytest.raises(FilesystemAccessError):
        service.read(root / "outside.txt")


def test_read_missing_file_raises_filesystem_operation_error(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    with pytest.raises(FilesystemOperationError):
        service.read(allowed_dir / "missing.txt")


def test_read_too_large_file_is_rejected(allowed_dir: Path, root: Path) -> None:
    config = FilesystemConfig(allowed_dirs=[Path("allowed")], max_read_bytes=10)
    service = LocalFilesystemService(config, root=root)
    target = allowed_dir / "big.txt"
    target.write_text("x" * 100, encoding="utf-8")
    with pytest.raises(FilesystemOperationError, match="max_read_bytes"):
        service.read(target)


# -- copy -----------------------------------------------------------------------


def test_copy_file(service: LocalFilesystemService, allowed_dir: Path) -> None:
    source = allowed_dir / "a.txt"
    source.write_text("data", encoding="utf-8")
    dest = allowed_dir / "b.txt"

    result = service.copy(source, dest)

    assert result.success is True
    assert dest.read_text(encoding="utf-8") == "data"
    assert source.exists()  # copy does not remove the original


def test_copy_directory_tree(service: LocalFilesystemService, allowed_dir: Path) -> None:
    source_dir = allowed_dir / "src"
    (source_dir / "nested").mkdir(parents=True)
    (source_dir / "nested" / "file.txt").write_text("x", encoding="utf-8")
    dest_dir = allowed_dir / "dst"

    service.copy(source_dir, dest_dir)

    assert (dest_dir / "nested" / "file.txt").read_text(encoding="utf-8") == "x"


def test_copy_denied_if_destination_outside_allowed_dir(
    service: LocalFilesystemService, allowed_dir: Path, root: Path
) -> None:
    source = allowed_dir / "a.txt"
    source.write_text("data", encoding="utf-8")
    with pytest.raises(FilesystemAccessError):
        service.copy(source, root / "outside.txt")


# -- move / rename / delete (require confirmation) -------------------------------


def test_move_without_confirmation_raises_and_does_not_move(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    source = allowed_dir / "a.txt"
    source.write_text("data", encoding="utf-8")
    dest = allowed_dir / "b.txt"

    with pytest.raises(ConfirmationRequiredError):
        service.move(source, dest)

    assert source.exists()
    assert not dest.exists()


def test_move_with_confirmation_succeeds(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    source = allowed_dir / "a.txt"
    source.write_text("data", encoding="utf-8")
    dest = allowed_dir / "b.txt"

    result = service.move(source, dest, confirmed=True)

    assert result.success is True
    assert not source.exists()
    assert dest.read_text(encoding="utf-8") == "data"


def test_rename_without_confirmation_raises(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    source = allowed_dir / "a.txt"
    source.write_text("data", encoding="utf-8")
    with pytest.raises(ConfirmationRequiredError):
        service.rename(source, "b.txt")
    assert source.exists()


def test_rename_with_confirmation_succeeds(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    source = allowed_dir / "a.txt"
    source.write_text("data", encoding="utf-8")

    result = service.rename(source, "b.txt", confirmed=True)

    assert result.success is True
    assert not source.exists()
    assert (allowed_dir / "b.txt").read_text(encoding="utf-8") == "data"


@pytest.mark.parametrize("bad_name", ["", ".", "..", "a/b", "a\\b"])
def test_rename_rejects_invalid_new_name(
    service: LocalFilesystemService, allowed_dir: Path, bad_name: str
) -> None:
    source = allowed_dir / "a.txt"
    source.write_text("data", encoding="utf-8")
    with pytest.raises(FilesystemOperationError):
        service.rename(source, bad_name, confirmed=True)


def test_delete_without_confirmation_raises_and_keeps_file(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    target = allowed_dir / "a.txt"
    target.write_text("data", encoding="utf-8")
    with pytest.raises(ConfirmationRequiredError):
        service.delete(target)
    assert target.exists()


def test_delete_with_confirmation_removes_file(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    target = allowed_dir / "a.txt"
    target.write_text("data", encoding="utf-8")

    result = service.delete(target, confirmed=True)

    assert result.success is True
    assert not target.exists()


def test_delete_directory_removes_recursively(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    directory = allowed_dir / "d"
    (directory / "nested").mkdir(parents=True)
    (directory / "nested" / "f.txt").write_text("x", encoding="utf-8")

    service.delete(directory, confirmed=True)

    assert not directory.exists()


def test_operations_outside_require_confirmation_list_need_no_confirmation(
    allowed_dir: Path, root: Path
) -> None:
    config = FilesystemConfig(allowed_dirs=[Path("allowed")], require_confirmation=[])
    service = LocalFilesystemService(config, root=root)
    target = allowed_dir / "a.txt"
    target.write_text("data", encoding="utf-8")

    service.delete(target)  # no ConfirmationRequiredError, since not in the configured set

    assert not target.exists()


# -- search -----------------------------------------------------------------------


def test_search_finds_matching_files(service: LocalFilesystemService, allowed_dir: Path) -> None:
    (allowed_dir / "a.txt").write_text("x", encoding="utf-8")
    (allowed_dir / "b.md").write_text("x", encoding="utf-8")

    matches = service.search(allowed_dir, "*.txt")

    assert [m.name for m in matches] == ["a.txt"]


def test_search_recursive_finds_nested_files(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    nested = allowed_dir / "sub"
    nested.mkdir()
    (nested / "c.txt").write_text("x", encoding="utf-8")

    matches = service.search(allowed_dir, "*.txt", recursive=True)

    assert any(m.name == "c.txt" for m in matches)


def test_search_non_recursive_does_not_find_nested_files(
    service: LocalFilesystemService, allowed_dir: Path
) -> None:
    nested = allowed_dir / "sub"
    nested.mkdir()
    (nested / "c.txt").write_text("x", encoding="utf-8")

    matches = service.search(allowed_dir, "*.txt", recursive=False)

    assert all(m.name != "c.txt" for m in matches)


def test_search_respects_max_search_results(allowed_dir: Path, root: Path) -> None:
    for i in range(10):
        (allowed_dir / f"f{i}.txt").write_text("x", encoding="utf-8")
    config = FilesystemConfig(allowed_dirs=[Path("allowed")], max_search_results=3)
    service = LocalFilesystemService(config, root=root)

    matches = service.search(allowed_dir, "*.txt")

    assert len(matches) == 3


def test_search_denied_outside_allowed_dir(service: LocalFilesystemService, root: Path) -> None:
    with pytest.raises(FilesystemAccessError):
        service.search(root, "*.txt")


# -- logging: every operation is logged --------------------------------------------


def test_successful_operation_is_logged(
    service: LocalFilesystemService, allowed_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="jarvis.core.filesystem.service"):
        service.write(allowed_dir / "a.txt", "x")
    assert any("succeeded" in record.message for record in caplog.records)


def test_denied_operation_is_logged(
    service: LocalFilesystemService, root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="jarvis.core.filesystem.service"):
        with pytest.raises(FilesystemAccessError):
            service.read(root / "outside.txt")
    assert any("denied" in record.message for record in caplog.records)


def test_confirmation_required_is_logged(
    service: LocalFilesystemService, allowed_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    target = allowed_dir / "a.txt"
    target.write_text("x", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="jarvis.core.filesystem.service"):
        with pytest.raises(ConfirmationRequiredError):
            service.delete(target)
    assert any("confirmation" in record.message for record in caplog.records)


def test_failed_operation_is_logged(
    service: LocalFilesystemService, allowed_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="jarvis.core.filesystem.service"):
        with pytest.raises(FilesystemOperationError):
            service.read(allowed_dir / "missing.txt")
    assert any("failed" in record.message for record in caplog.records)


# -- events --------------------------------------------------------------------------


def test_successful_operation_publishes_event(
    service: LocalFilesystemService, allowed_dir: Path, fs_events: EventBus
) -> None:
    received = []
    fs_events.subscribe("filesystem.operation_succeeded", received.append)
    service.write(allowed_dir / "a.txt", "x")
    assert len(received) == 1
    assert received[0].payload["operation"] == "write"


def test_denied_operation_publishes_event(
    service: LocalFilesystemService, root: Path, fs_events: EventBus
) -> None:
    received = []
    fs_events.subscribe("filesystem.denied", received.append)
    with pytest.raises(FilesystemAccessError):
        service.read(root / "outside.txt")
    assert len(received) == 1


def test_confirmation_required_publishes_event(
    service: LocalFilesystemService, allowed_dir: Path, fs_events: EventBus
) -> None:
    target = allowed_dir / "a.txt"
    target.write_text("x", encoding="utf-8")
    received = []
    fs_events.subscribe("filesystem.confirmation_required", received.append)
    with pytest.raises(ConfirmationRequiredError):
        service.delete(target)
    assert len(received) == 1
