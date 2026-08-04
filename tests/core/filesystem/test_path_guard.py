from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.filesystem_config import FilesystemConfig
from jarvis.core.exceptions import FilesystemAccessError
from jarvis.core.filesystem.path_guard import PROTECTED_SYSTEM_PATHS, PathGuard


def test_path_inside_allowed_dir_is_permitted(
    allowed_dir: Path, fs_config: FilesystemConfig, root: Path
) -> None:
    guard = PathGuard(fs_config, root=root)
    resolved = guard.check(allowed_dir / "notes.txt")
    assert resolved == (allowed_dir / "notes.txt").resolve()


def test_path_outside_allowed_dirs_is_denied(fs_config: FilesystemConfig, root: Path) -> None:
    guard = PathGuard(fs_config, root=root)
    with pytest.raises(FilesystemAccessError):
        guard.check(root / "elsewhere" / "notes.txt")


def test_relative_path_resolves_against_root_not_cwd(
    allowed_dir: Path, fs_config: FilesystemConfig, root: Path
) -> None:
    guard = PathGuard(fs_config, root=root)
    # A relative path, resolved against `root` (allowed), must never be
    # silently reinterpreted against the process's actual CWD.
    resolved = guard.check(Path("allowed") / "x.txt")
    assert resolved == (allowed_dir / "x.txt").resolve()


def test_blacklisted_subdir_denied_even_inside_allowed_dir(allowed_dir: Path, root: Path) -> None:
    config = FilesystemConfig(
        allowed_dirs=[Path("allowed")], blacklisted_dirs=[Path("allowed") / "secret"]
    )
    guard = PathGuard(config, root=root)
    with pytest.raises(FilesystemAccessError):
        guard.check(allowed_dir / "secret" / "x.txt")


def test_blacklist_does_not_affect_sibling_paths(allowed_dir: Path, root: Path) -> None:
    config = FilesystemConfig(
        allowed_dirs=[Path("allowed")], blacklisted_dirs=[Path("allowed") / "secret"]
    )
    guard = PathGuard(config, root=root)
    assert guard.check(allowed_dir / "public.txt") == (allowed_dir / "public.txt").resolve()


@pytest.mark.parametrize(
    "candidate",
    [
        r"C:\Windows\notes.txt",
        r"C:\Windows\System32\drivers\etc\hosts",
        r"C:\Windows\System32\config\SAM",
        r"C:\Program Files\SomeApp\config.ini",
    ],
)
def test_protected_system_paths_are_always_denied_even_if_allowlisted(
    candidate: str, root: Path
) -> None:
    # Even a maximally permissive (or misconfigured) allowlist must not
    # be able to override the hardcoded protection.
    config = FilesystemConfig(allowed_dirs=[Path("C:/")], blacklisted_dirs=[])
    guard = PathGuard(config, root=root)
    with pytest.raises(FilesystemAccessError, match="protected system path"):
        guard.check(candidate)


def test_protected_system_paths_include_windows_program_files_system32_and_registry() -> None:
    protected_strs = [str(p).lower() for p in PROTECTED_SYSTEM_PATHS]
    assert any("windows" in p for p in protected_strs)
    assert any("system32" in p for p in protected_strs)
    assert any("program files" in p for p in protected_strs)
    assert any("config" in p for p in protected_strs)  # registry hive directory


def test_empty_allowlist_denies_everything(root: Path) -> None:
    config = FilesystemConfig(allowed_dirs=[], blacklisted_dirs=[])
    guard = PathGuard(config, root=root)
    with pytest.raises(FilesystemAccessError):
        guard.check(root / "anything.txt")


def test_check_does_not_require_target_to_exist(
    allowed_dir: Path, fs_config: FilesystemConfig, root: Path
) -> None:
    guard = PathGuard(fs_config, root=root)
    # A write/copy/move destination legitimately doesn't exist yet.
    resolved = guard.check(allowed_dir / "does_not_exist_yet.txt")
    assert resolved.name == "does_not_exist_yet.txt"
