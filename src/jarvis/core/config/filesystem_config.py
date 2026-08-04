"""filesystem.yaml — allowlist/blacklist directories for the filesystem
module, plus which operations require explicit confirmation.

This is the sixth config domain, added without changing
core/config/loader.py or ConfigManager's public shape at all — exactly
the extensibility Phase 3 was built for (see loader.py's module
docstring: "a sixth domain added later only needs a model class, not
new plumbing").

Defaults intentionally allow only the app's own storage areas (`data`,
`vault` — the same directories settings.yaml's `paths` section
designates), not the whole filesystem: `allowed_dirs` is a genuine
allowlist, and an empty one would deny everything, which is safe but
useless out of the box. Anything outside `allowed_dirs` stays denied
regardless of this default. See core/filesystem/path_guard.py for the
enforcement itself, including the hardcoded (non-configurable)
protection of Windows/Program Files/System32/the registry.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

FILESYSTEM_FILENAME = "filesystem.yaml"

_DEFAULT_REQUIRE_CONFIRMATION = ("delete", "move", "rename")


class FilesystemConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    allowed_dirs: list[Path] = Field(default_factory=lambda: [Path("data"), Path("vault")])
    blacklisted_dirs: list[Path] = Field(default_factory=list)
    require_confirmation: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_REQUIRE_CONFIRMATION)
    )
    max_read_bytes: int = Field(10_000_000, gt=0)
    max_search_results: int = Field(1000, gt=0)
