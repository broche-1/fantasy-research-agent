"""Persistence helpers for OAuth tokens."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import json


@dataclass
class OAuthTokens:
    """Typed representation of OAuth2 token payload."""

    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str = "bearer"
    scope: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dict."""
        payload: Dict[str, Any] = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
        }
        if self.scope:
            payload["scope"] = self.scope
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthTokens":
        """Create OAuthTokens from persisted dictionary."""
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_at=float(data["expires_at"]),
            token_type=data.get("token_type", "bearer"),
            scope=data.get("scope"),
        )


class TokenStore:
    """File-based storage for OAuth tokens."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Optional[OAuthTokens]:
        """Return tokens if they exist on disk."""
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return OAuthTokens.from_dict(data)

    def save(self, tokens: OAuthTokens) -> None:
        """Persist tokens to disk, creating directories as needed."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(tokens.to_dict(), indent=2), encoding="utf-8")
