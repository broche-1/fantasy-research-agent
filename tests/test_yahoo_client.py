"""Unit tests for YahooClient OAuth helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import pytest

from data_fetcher.cache import LocalCache
from data_fetcher.token_store import OAuthTokens, TokenStore
from data_fetcher.yahoo_client import YahooClient, YahooConfig


class MockResponse:
    """Minimal mock of requests.Response."""

    def __init__(self, payload: Dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)
        self.headers: Dict[str, str] = {}

    def json(self) -> Dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


class MockSession:
    """Queue-based mock for requests.Session."""

    def __init__(
        self,
        post_responses: Optional[List[MockResponse]] = None,
        get_responses: Optional[List[MockResponse]] = None,
    ) -> None:
        self.post_calls: List[Dict[str, Any]] = []
        self.get_calls: List[Dict[str, Any]] = []
        self._post_responses = post_responses or []
        self._get_responses = get_responses or []

    def post(self, url: str, **kwargs: Any) -> MockResponse:
        self.post_calls.append({"url": url, "kwargs": kwargs})
        if not self._post_responses:
            raise AssertionError("Unexpected POST call.")
        return self._post_responses.pop(0)

    def get(self, url: str, **kwargs: Any) -> MockResponse:
        self.get_calls.append({"url": url, "kwargs": kwargs})
        if not self._get_responses:
            raise AssertionError("Unexpected GET call.")
        return self._get_responses.pop(0)


def build_client(tmp_path: Path, session: MockSession) -> YahooClient:
    """Helper to construct a YahooClient for tests."""
    config = YahooConfig(
        client_id="client",
        client_secret="secret",
        redirect_uri="http://localhost/callback",
        league_id="12345",
        team_id="7",
    )
    store = TokenStore(tmp_path / "tokens.json")
    cache = LocalCache(tmp_path / "cache")
    return YahooClient(config=config, token_store=store, session=session, cache=cache)


def test_authorization_url_contains_required_parameters(tmp_path: Path) -> None:
    session = MockSession()
    client = build_client(tmp_path, session)

    url = client.get_authorization_url(state="xyz")

    assert "client_id=client" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%2Fcallback" in url
    assert "state=xyz" in url


def test_exchange_code_persists_tokens(tmp_path: Path) -> None:
    session = MockSession(
        post_responses=[
            MockResponse(
                {
                    "access_token": "abc123",
                    "refresh_token": "refresh123",
                    "expires_in": 3600,
                    "token_type": "bearer",
                }
            )
        ]
    )
    client = build_client(tmp_path, session)

    tokens = client.exchange_code_for_token("authcode")

    assert tokens.access_token == "abc123"
    persisted = client.token_store.load()
    assert persisted is not None
    assert persisted.refresh_token == "refresh123"


def test_refresh_access_token_preserves_refresh_token_when_missing(tmp_path: Path) -> None:
    session = MockSession(
        post_responses=[
            MockResponse(
                {
                    "access_token": "new-token",
                    "expires_in": 3600,
                }
            )
        ]
    )
    client = build_client(tmp_path, session)
    client.token_store.save(
        OAuthTokens(
            access_token="old-token",
            refresh_token="existing-refresh",
            expires_at=time.time() - 10,  # expired
        )
    )

    tokens = client.refresh_access_token()

    assert tokens.access_token == "new-token"
    assert tokens.refresh_token == "existing-refresh"


def test_authenticate_refreshes_expired_token(tmp_path: Path) -> None:
    session = MockSession(
        post_responses=[
            MockResponse(
                {
                    "access_token": "new-token",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                }
            )
        ]
    )
    client = build_client(tmp_path, session)
    client.token_store.save(
        OAuthTokens(
            access_token="stale",
            refresh_token="refresh",
            expires_at=time.time() - 1,
        )
    )

    tokens = client.authenticate()

    assert tokens.access_token == "new-token"
    assert session.post_calls, "Expected refresh POST call."


def test_fetch_league_metadata_returns_payload(tmp_path: Path) -> None:
    active_tokens = OAuthTokens(
        access_token="token",
        refresh_token="refresh",
        expires_at=time.time() + 3600,
    )

    session = MockSession(
        get_responses=[
            MockResponse({"fantasy_content": {"league": []}}),
        ]
    )
    client = build_client(tmp_path, session)
    client.token_store.save(active_tokens)

    payload = client.fetch_league_metadata()

    assert "fantasy_content" in payload
    assert session.get_calls[0]["kwargs"]["headers"]["Authorization"] == "Bearer token"


def test_fetch_team_roster_uses_week_parameter_and_cache(tmp_path: Path) -> None:
    active_tokens = OAuthTokens(
        access_token="token",
        refresh_token="refresh",
        expires_at=time.time() + 3600,
    )
    session = MockSession(
        get_responses=[
            MockResponse({"fantasy_content": {"team": []}}),
        ]
    )
    client = build_client(tmp_path, session)
    client.token_store.save(active_tokens)

    payload = client.fetch_team_roster(week=2)

    assert "fantasy_content" in payload
    assert "roster;week=2" in session.get_calls[0]["url"]

    # Second call should hit cache, not session.
    payload_again = client.fetch_team_roster(week=2)
    assert payload_again == payload
    assert len(session.get_calls) == 1


def test_fetch_matchup_results_fetches_scoreboard_with_cache(tmp_path: Path) -> None:
    active_tokens = OAuthTokens(
        access_token="token",
        refresh_token="refresh",
        expires_at=time.time() + 3600,
    )
    session = MockSession(
        get_responses=[
            MockResponse({"fantasy_content": {"scoreboard": []}}),
        ]
    )
    client = build_client(tmp_path, session)
    client.token_store.save(active_tokens)

    data = client.fetch_matchup_results(week=3)

    assert "scoreboard" in data["fantasy_content"]
    assert "scoreboard;week=3" in session.get_calls[0]["url"]

    cached = client.fetch_matchup_results(week=3)
    assert cached == data
    assert len(session.get_calls) == 1


def test_fetch_league_settings_uses_cache(tmp_path: Path) -> None:
    active_tokens = OAuthTokens(
        access_token="token",
        refresh_token="refresh",
        expires_at=time.time() + 3600,
    )
    session = MockSession(
        get_responses=[
            MockResponse({"fantasy_content": {"league": []}}),
        ]
    )
    client = build_client(tmp_path, session)
    client.token_store.save(active_tokens)

    payload = client.fetch_league_settings(use_cache=True)

    assert "fantasy_content" in payload
    assert "settings" in session.get_calls[0]["url"]

    cached = client.fetch_league_settings(use_cache=True)
    assert cached == payload
    assert len(session.get_calls) == 1


def test_fetch_player_stats_requires_player_keys(tmp_path: Path) -> None:
    session = MockSession()
    client = build_client(tmp_path, session)

    with pytest.raises(ValueError):
        client.fetch_player_stats([])


def test_fetch_player_stats_sorts_keys_and_uses_cache(tmp_path: Path) -> None:
    active_tokens = OAuthTokens(
        access_token="token",
        refresh_token="refresh",
        expires_at=time.time() + 3600,
    )
    session = MockSession(
        get_responses=[
            MockResponse({"fantasy_content": {"players": []}}),
        ]
    )
    client = build_client(tmp_path, session)
    client.token_store.save(active_tokens)

    data = client.fetch_player_stats(["nfl.p.1", "nfl.p.2"], week=4)

    assert "players" in data["fantasy_content"]
    first_call_url = session.get_calls[0]["url"]
    assert "players;player_keys=nfl.p.1,nfl.p.2/stats;type=week;week=4" in first_call_url

    # Reverse order should still hit cache thanks to sorting.
    cached = client.fetch_player_stats(["nfl.p.2", "nfl.p.1"], week=4)
    assert cached == data
    assert len(session.get_calls) == 1


def test_fetch_free_agents_uses_status_and_cache(tmp_path: Path) -> None:
    active_tokens = OAuthTokens(
        access_token="token",
        refresh_token="refresh",
        expires_at=time.time() + 3600,
    )
    session = MockSession(
        get_responses=[
            MockResponse(
                {
                    "fantasy_content": {
                        "league": [
                            {},
                            {"players": {"0": {"player": [[{"player_key": "461.p.1"}]]}, "count": 1}},
                        ]
                    }
                }
            )
        ]
    )
    client = build_client(tmp_path, session)
    client.token_store.save(active_tokens)

    payload = client.fetch_free_agents(week=8, status="A", count=5)

    assert "fantasy_content" in payload
    first_call = session.get_calls[0]
    assert "status=A;count=5" in first_call["url"]
    assert first_call["kwargs"]["params"]["sort"] == "PTS"

    cached = client.fetch_free_agents(week=8, status="A", count=5)
    assert cached == payload
    assert len(session.get_calls) == 1
