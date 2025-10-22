"""Simple JSON file cache for Yahoo API responses."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional


class LocalCache:
    """Persist JSON payloads locally with optional max-age expiry."""

    def __init__(self, directory: Path, *, max_age_seconds: Optional[int] = None) -> None:
        self.directory = directory
        self.max_age_seconds = max_age_seconds

    def load(self, key: str) -> Optional[dict[str, Any]]:
        """Return cached payload if it exists and is still fresh."""
        path = self._path_for(key)
        if not path.exists():
            return None

        if self.max_age_seconds is not None:
            age = time.time() - path.stat().st_mtime
            if age > self.max_age_seconds:
                return None

        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def save(self, key: str, payload: dict[str, Any]) -> None:
        """Persist payload to disk."""
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _path_for(self, key: str) -> Path:
        safe_key = self._sanitize(key)
        return self.directory / f"{safe_key}.json"

    @staticmethod
    def _sanitize(value: str) -> str:
        return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value)

