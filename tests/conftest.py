"""Pytest configuration for adjusting import paths."""

from __future__ import annotations

import sys
from pathlib import Path


def pytest_configure() -> None:
    """Ensure the src/ directory is importable without installing the package."""
    root = Path(__file__).resolve().parents[1]
    src_dir = root / "src"
    src_path = str(src_dir)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
