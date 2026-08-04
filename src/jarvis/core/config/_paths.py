"""Shared path constants for the config package.

Split into its own module (rather than living in one of the domain
files) so every domain module and manager.py can import PROJECT_ROOT /
DEFAULT_CONFIG_DIR without importing each other.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"
