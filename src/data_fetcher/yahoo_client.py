"""Yahoo Fantasy Sports API client with OAuth2 support."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlencode

import requests

from .cache import LocalCache
from .token_store import OAuthTokens, TokenStore

AUTH_SCOPE = "fspt-r"  # Read-only Fantasy Sports data
DEFAULT_AUTH_URL = "https://api.login.yahoo.com/oauth2/request_auth"
DEFAULT_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
DEFAULT_API_BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"


@dataclass()
class YahooConfig:
    """Container for Yahoo OAuth settings."""

    client_id: str
    client_secret: str
    redirect_uri: str
    league_id: Optional[str] = None
    team_id: Optional[str] = None
    scope: str = AUTH_SCOPE
    auth_url: str = DEFAULT_AUTH_URL
    token_url: str = DEFAULT_TOKEN_URL
    api_base_url: str = DEFAULT_API_BASE_URL

    @property
    def league_key(self) -> Optional[str]:
        """Return league key derived from the numeric league id."""
        if not self.league_id:
            return None
        # Fantasy Football leagues use the nfl namespace.
        return f"nfl.l.{self.league_id}"

    @property
    def team_key(self) -> Optional[str]:
        """Return team key derived from the league and team identifiers."""
        if not self.league_key or not self.team_id:
            return None
        return f"{self.league_key}.t.{self.team_id}"


class YahooClient:
    """Handle Yahoo Fantasy Sports API requests."""

    def __init__(
        self,
        config: YahooConfig,
        token_store: TokenStore,
        session: Optional[requests.Session] = None,
        cache: Optional[LocalCache] = None,
    ) -> None:
        self.config = config
        self.token_store = token_store
        self.session = session or requests.Session()
        self.cache = cache

    @classmethod
    def from_env(
        cls,
        token_store_path: Optional[Path] = None,
        *,
        scope: str = AUTH_SCOPE,
        auth_url: str = DEFAULT_AUTH_URL,
        token_url: str = DEFAULT_TOKEN_URL,
        api_base_url: str = DEFAULT_API_BASE_URL,
    ) -> "YahooClient":
        """Instantiate a client using environment variables."""
        try:
            client_id = os.environ["YAHOO_CLIENT_ID"]
            client_secret = os.environ["YAHOO_CLIENT_SECRET"]
            redirect_uri = os.environ["YAHOO_REDIRECT_URI"]
        except KeyError as exc:  # pragma: no cover - defensive path
            missing = exc.args[0]
            raise RuntimeError(f"Missing Yahoo OAuth environment variable: {missing}") from exc

        league_id = os.environ.get("YAHOO_LEAGUE_ID")
        team_id = os.environ.get("YAHOO_TEAM_ID")

        config = YahooConfig(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            league_id=league_id,
            team_id=team_id,
            scope=scope,
            auth_url=auth_url,
            token_url=token_url,
            api_base_url=api_base_url,
        )

        store_path = token_store_path or Path("config/tokens.json")
        token_store = TokenStore(store_path)
        cache_dir = Path(os.environ.get("YAHOO_CACHE_DIR", "config/cache"))
        max_age_env = os.environ.get("YAHOO_CACHE_MAX_AGE")
        max_age = int(max_age_env) if max_age_env else None
        cache = LocalCache(cache_dir, max_age_seconds=max_age)
        return cls(config=config, token_store=token_store, cache=cache)

    # ------------------------------------------------------------------
    # OAuth flows
    # ------------------------------------------------------------------

    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """Return Yahoo authorization URL to initiate OAuth consent."""
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": self.config.scope,
        }
        if state:
            params["state"] = state
        return f"{self.config.auth_url}?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> OAuthTokens:
        """Exchange authorization code for access and refresh tokens."""
        response = self.session.post(
            self.config.token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.config.redirect_uri,
            },
            auth=(self.config.client_id, self.config.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        tokens = self._build_token_payload(payload)
        self.token_store.save(tokens)
        return tokens

    def refresh_access_token(self) -> OAuthTokens:
        """Refresh the access token using the stored refresh token."""
        current_tokens = self.token_store.load()
        if not current_tokens:
            raise RuntimeError("Cannot refresh token: no existing refresh token found.")

        response = self.session.post(
            self.config.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": current_tokens.refresh_token,
            },
            auth=(self.config.client_id, self.config.client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        response.raise_for_status()

        payload = response.json()
        # Yahoo may not always return a new refresh token; preserve the old one.
        refresh_token = payload.get("refresh_token", current_tokens.refresh_token)
        payload.setdefault("refresh_token", refresh_token)

        tokens = self._build_token_payload(payload)
        self.token_store.save(tokens)
        return tokens

    def authenticate(self) -> OAuthTokens:
        """Ensure valid OAuth tokens are available, refreshing if necessary."""
        tokens = self.token_store.load()
        if tokens and not self._is_token_expired(tokens):
            return tokens
        if tokens:
            return self.refresh_access_token()
        raise RuntimeError(
            "No OAuth tokens available. Run the authorization bootstrap tool first."
        )

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    def fetch_league_metadata(self, league_key: Optional[str] = None) -> Dict[str, Any]:
        """Fetch league details for the configured or specified league."""
        resolved_key = league_key or self.config.league_key
        if not resolved_key:
            raise ValueError("A league key is required to fetch league metadata.")

        cache_key = self._cache_key("league_metadata", resolved_key)
        path = f"league/{resolved_key}"
        return self._get_json(path, cache_key=cache_key)

    def fetch_league_settings(
        self,
        league_key: Optional[str] = None,
        *,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Fetch league settings (stat modifiers, roster rules, etc.)."""
        resolved_key = league_key or self.config.league_key
        if not resolved_key:
            raise ValueError("A league key is required to fetch league settings.")

        path = f"league/{resolved_key}/settings"
        cache_key = self._cache_key("league_settings", resolved_key)
        return self._get_json(path, cache_key=cache_key, use_cache=use_cache)

    def fetch_team_roster(
        self,
        week: Optional[int] = None,
        team_key: Optional[str] = None,
        *,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Fetch roster details for a team and optional week."""
        resolved_team_key = team_key or self.config.team_key
        if not resolved_team_key:
            raise ValueError("A team key is required to fetch roster data.")

        week_segment = f";week={week}" if week is not None else ""
        cache_parts = [resolved_team_key, f"week-{week}" if week is not None else "current"]
        cache_key = self._cache_key("team_roster", *cache_parts)
        path = f"team/{resolved_team_key}/roster{week_segment}"
        return self._get_json(path, cache_key=cache_key, use_cache=use_cache)

    def fetch_matchup_results(
        self,
        week: int,
        league_key: Optional[str] = None,
        *,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Fetch scoreboard results for a league week."""
        resolved_key = league_key or self.config.league_key
        if not resolved_key:
            raise ValueError("A league key is required to fetch matchup results.")

        path = f"league/{resolved_key}/scoreboard;week={week}"
        cache_key = self._cache_key("scoreboard", resolved_key, str(week))
        return self._get_json(path, cache_key=cache_key, use_cache=use_cache)

    def fetch_player_stats(
        self,
        player_keys: Iterable[str],
        *,
        week: Optional[int] = None,
        stat_type: str = "week",
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Fetch stats for one or more players."""
        keys = list(player_keys)
        if not keys:
            raise ValueError("At least one player key is required.")

        sorted_keys = sorted(keys)
        joined_keys = ",".join(sorted_keys)
        stats_segment = ""
        cache_suffix: list[str] = []
        if stat_type:
            stats_segment = f";type={stat_type}"
            cache_suffix.append(stat_type)
        if week is not None:
            stats_segment += f";week={week}"
            cache_suffix.append(str(week))

        cache_parts = [",".join(sorted_keys)]
        if cache_suffix:
            cache_parts.append("-".join(cache_suffix))
        cache_key = self._cache_key("player_stats", *cache_parts)
        path = f"players;player_keys={joined_keys}/stats{stats_segment}"
        return self._get_json(path, cache_key=cache_key, use_cache=use_cache)

    def fetch_free_agents(
        self,
        week: Optional[int],
        league_key: Optional[str] = None,
        *,
        status: str = "A",
        count: int = 10,
        sort: str = "PTS",
        sort_type: str = "season",
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Fetch available players (free agents or waivers) for the league."""
        resolved_key = league_key or self.config.league_key
        if not resolved_key:
            raise ValueError("A league key is required to fetch free agents.")

        path = f"league/{resolved_key}/players;status={status};count={count}"
        params: Dict[str, Any] = {
            "sort": sort,
            "sort_type": sort_type,
        }
        if week is not None:
            params["week"] = week

        cache_key = self._cache_key(
            "free_agents",
            resolved_key,
            status,
            sort,
            sort_type,
            str(week) if week is not None else "all",
            str(count),
        )
        return self._get_json(path, params=params, cache_key=cache_key, use_cache=use_cache)

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    def _auth_headers(self, tokens: OAuthTokens) -> Dict[str, str]:
        return {"Authorization": f"Bearer {tokens.access_token}"}

    def _is_token_expired(self, tokens: OAuthTokens) -> bool:
        # Refresh one minute early as a buffer.
        return tokens.expires_at <= time.time() + 60

    def _build_token_payload(self, payload: Dict[str, Any]) -> OAuthTokens:
        expires_in = int(payload.get("expires_in", 3600))
        expires_at = time.time() + expires_in
        return OAuthTokens(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_at=expires_at,
            token_type=payload.get("token_type", "bearer"),
            scope=payload.get("scope"),
        )

    def _get_json(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        cache_key: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        if use_cache and cache_key and self.cache:
            cached = self.cache.load(cache_key)
            if cached is not None:
                return cached

        tokens = self.authenticate()
        url = f"{self.config.api_base_url}/{path.lstrip('/')}"
        response = self.session.get(
            url,
            params=self._build_params(params),
            headers=self._auth_headers(tokens),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()

        if cache_key and self.cache and use_cache:
            self.cache.save(cache_key, payload)
        return payload

    @staticmethod
    def _build_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        base = {"format": "json"}
        if params:
            base.update(params)
        return base

    @staticmethod
    def _cache_key(prefix: str, *parts: str) -> str:
        sanitized_parts = [part.replace(".", "_").replace(" ", "_") for part in parts if part]
        if not sanitized_parts:
            return prefix
        return "__".join([prefix, *sanitized_parts])
