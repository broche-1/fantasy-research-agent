"""CLI utilities for the Fantasy Football Research Assistant."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

import requests

from data_fetcher.yahoo_client import YahooClient
from data_processor.metrics import summarize_week
from report_generator.markdown import render_report


def build_parser() -> argparse.ArgumentParser:
    """Create command-line parser."""
    parser = argparse.ArgumentParser(
        description="Yahoo Fantasy Football OAuth and data helper.",
    )
    parser.add_argument(
        "--token-store",
        type=Path,
        default=None,
        help="Path to OAuth token cache file (default: config/tokens.json).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_url_parser = subparsers.add_parser(
        "auth-url", help="Print the Yahoo authorization URL."
    )
    auth_url_parser.add_argument(
        "--state",
        help="Optional state parameter for CSRF protection.",
    )

    exchange_parser = subparsers.add_parser(
        "exchange-code", help="Exchange an authorization code for tokens."
    )
    exchange_parser.add_argument("--code", required=True, help="Authorization code.")

    subparsers.add_parser("refresh", help="Refresh the access token.")

    league_parser = subparsers.add_parser(
        "league-metadata",
        help="Fetch league metadata to verify API access.",
    )
    league_parser.add_argument(
        "--league-key",
        help="Explicit league key (defaults to value derived from YAHOO_LEAGUE_ID).",
    )
    league_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON response.",
    )

    settings_parser = subparsers.add_parser(
        "league-settings",
        help="Fetch league settings (stat modifiers, roster rules).",
    )
    settings_parser.add_argument(
        "--league-key",
        help="Explicit league key (defaults to value derived from YAHOO_LEAGUE_ID).",
    )
    settings_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass local cache and fetch fresh data.",
    )
    settings_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON response.",
    )

    roster_parser = subparsers.add_parser(
        "team-roster",
        help="Fetch team roster details.",
    )
    roster_parser.add_argument("--team-key", help="Explicit team key to query.")
    roster_parser.add_argument(
        "--week",
        type=int,
        help="Optional scoring week; defaults to current.",
    )
    roster_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass local cache and fetch fresh data.",
    )
    roster_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON response.",
    )

    scoreboard_parser = subparsers.add_parser(
        "scoreboard",
        help="Fetch league scoreboard for a given week.",
    )
    scoreboard_parser.add_argument(
        "--league-key",
        help="Explicit league key (defaults to value derived from YAHOO_LEAGUE_ID).",
    )
    scoreboard_parser.add_argument(
        "--week",
        required=True,
        type=int,
        help="Scoring week to retrieve.",
    )
    scoreboard_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass local cache and fetch fresh data.",
    )
    scoreboard_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON response.",
    )

    stats_parser = subparsers.add_parser(
        "player-stats",
        help="Fetch player statistics for specified player keys.",
    )
    stats_parser.add_argument(
        "player_keys",
        nargs="+",
        help="One or more Yahoo player keys (e.g. nfl.p.1234).",
    )
    stats_parser.add_argument(
        "--week",
        type=int,
        help="Optional scoring week (defaults to season totals).",
    )
    stats_parser.add_argument(
        "--stat-type",
        default="week",
        help="Stat type context when week is provided (default: week).",
    )
    stats_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass local cache and fetch fresh data.",
    )
    stats_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON response.",
    )

    summary_parser = subparsers.add_parser(
        "summarize-week",
        help="Fetch data and output computed weekly insights.",
    )
    summary_parser.add_argument(
        "--week",
        type=int,
        help="Scoring week to summarize (defaults to league current week).",
    )
    summary_parser.add_argument(
        "--team-key",
        help="Explicit team key (defaults to value derived from YAHOO_TEAM_ID).",
    )
    summary_parser.add_argument(
        "--league-key",
        help="Explicit league key (defaults to value derived from YAHOO_LEAGUE_ID).",
    )
    summary_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bypass local cache and fetch fresh data.",
    )
    summary_parser.add_argument(
        "--use-fixtures",
        action="store_true",
        help="Load data from fixtures/ instead of hitting the Yahoo API.",
    )
    summary_parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=Path("fixtures"),
        help="Directory containing fixture JSON files (default: fixtures/).",
    )
    summary_parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file to write summary JSON.",
    )
    summary_parser.add_argument(
        "--free-agent-count",
        type=int,
        default=10,
        help="Number of available players to evaluate for waiver suggestions.",
    )
    summary_parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format (default: json).",
    )
    summary_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON response.",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Entrypoint for CLI execution."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        client = YahooClient.from_env(token_store_path=args.token_store)
    except RuntimeError as exc:
        parser.error(str(exc))

    try:
        if args.command == "auth-url":
            url = client.get_authorization_url(state=args.state)
            print(url)
            return 0

        if args.command == "exchange-code":
            tokens = client.exchange_code_for_token(args.code)
            print("Access token saved.")
            print(f"Expires at: {tokens.expires_at:.0f}")
            return 0

        if args.command == "refresh":
            tokens = client.refresh_access_token()
            print("Access token refreshed.")
            print(f"Expires at: {tokens.expires_at:.0f}")
            return 0

        if args.command == "league-metadata":
            data = client.fetch_league_metadata(league_key=args.league_key)
            _print_json(data, pretty=args.pretty)
            return 0

        if args.command == "league-settings":
            data = client.fetch_league_settings(
                league_key=args.league_key,
                use_cache=not args.no_cache,
            )
            _print_json(data, pretty=args.pretty)
            return 0

        if args.command == "team-roster":
            data = client.fetch_team_roster(
                week=args.week,
                team_key=args.team_key,
                use_cache=not args.no_cache,
            )
            _print_json(data, pretty=args.pretty)
            return 0

        if args.command == "scoreboard":
            data = client.fetch_matchup_results(
                week=args.week,
                league_key=args.league_key,
                use_cache=not args.no_cache,
            )
            _print_json(data, pretty=args.pretty)
            return 0

        if args.command == "player-stats":
            data = client.fetch_player_stats(
                args.player_keys,
                week=args.week,
                stat_type=args.stat_type,
                use_cache=not args.no_cache,
            )
            _print_json(data, pretty=args.pretty)
            return 0

        if args.command == "summarize-week":
            summary = _summarize_week_command(client, args)
            if args.format == "markdown":
                document = render_report(summary)
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_text(document, encoding="utf-8")
                else:
                    print(document, end="")
            else:
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    rendered = json.dumps(summary, indent=2 if args.pretty else None)
                    args.output.write_text(rendered, encoding="utf-8")
                else:
                    _print_json(summary, pretty=args.pretty)
            return 0

        parser.error("Unknown command.")
    except requests.HTTPError as exc:
        response = exc.response
        status = response.status_code if response else "unknown"
        print(f"HTTP error ({status}): {exc}", file=sys.stderr)
        if response is not None:
            try:
                print(response.text, file=sys.stderr)
            except Exception:  # pragma: no cover - best effort logging
                pass
        return 1
    except Exception as exc:  # pragma: no cover - defensive logging
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _print_json(payload: dict[str, Any], *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, indent=2))
    else:
        print(json.dumps(payload))


def _summarize_week_command(client: YahooClient, args: argparse.Namespace) -> dict[str, Any]:
    if args.use_fixtures:
        fixtures = _load_fixtures(args.fixtures_dir)
        payload = {
            "roster": fixtures["roster"],
            "scoreboard": fixtures["scoreboard"],
            "player_stats": fixtures.get("player_stats"),
            "season_player_stats": fixtures.get("season_player_stats"),
            "league_settings": fixtures.get("league_settings"),
            "team_key": args.team_key,
            "free_agents": fixtures.get("free_agents"),
            "free_agent_player_stats": fixtures.get("free_agent_player_stats"),
        }
        return summarize_week(payload)

    week = args.week or _infer_current_week(client, args.league_key)

    roster = client.fetch_team_roster(
        week=week,
        team_key=args.team_key,
        use_cache=not args.no_cache,
    )
    player_keys = _extract_editorial_player_keys(roster)
    player_stats = None
    if player_keys:
        player_stats = client.fetch_player_stats(
            player_keys,
            week=week,
            use_cache=not args.no_cache,
        )
    season_player_stats = None
    if player_keys:
        season_player_stats = client.fetch_player_stats(
            player_keys,
            stat_type="season",
            use_cache=not args.no_cache,
        )
    scoreboard = client.fetch_matchup_results(
        week=week,
        league_key=args.league_key,
        use_cache=not args.no_cache,
    )
    league_settings = client.fetch_league_settings(
        league_key=args.league_key,
        use_cache=not args.no_cache,
    )

    free_agents = client.fetch_free_agents(
        week=week,
        league_key=args.league_key,
        count=args.free_agent_count,
        use_cache=not args.no_cache,
    )
    free_agent_stats = None
    free_agent_keys = _extract_free_agent_player_keys(free_agents)
    if free_agent_keys:
        free_agent_stats = client.fetch_player_stats(
            free_agent_keys,
            stat_type="season",
            use_cache=not args.no_cache,
        )

    payload = {
        "roster": roster,
        "scoreboard": scoreboard,
        "player_stats": player_stats,
        "season_player_stats": season_player_stats,
        "league_settings": league_settings,
        "team_key": args.team_key,
        "free_agents": free_agents,
        "free_agent_player_stats": free_agent_stats,
    }
    return summarize_week(payload)


def _infer_current_week(client: YahooClient, league_key: Optional[str]) -> int:
    metadata = client.fetch_league_metadata(league_key=league_key)
    league = metadata.get("fantasy_content", {}).get("league")
    if isinstance(league, list) and league:
        current_week = league[0].get("current_week")
        if isinstance(current_week, int):
            return current_week
        if isinstance(current_week, str) and current_week.isdigit():
            return int(current_week)
    raise RuntimeError("Unable to determine current week from league metadata.")


def _extract_editorial_player_keys(roster_payload: dict[str, Any]) -> list[str]:
    team_section = roster_payload.get("fantasy_content", {}).get("team")
    if not isinstance(team_section, list):
        return []

    roster_block: Optional[dict[str, Any]] = None
    for item in team_section:
        if isinstance(item, dict) and "roster" in item:
            roster_block = item["roster"]
            break
    if not isinstance(roster_block, dict):
        return []

    players_container = roster_block.get("0", {}).get("players")
    if not isinstance(players_container, dict):
        return []

    try:
        count = int(players_container.get("count", 0))
    except (TypeError, ValueError):
        count = 0

    keys: list[str] = []
    for index in range(count):
        player_entry = players_container.get(str(index), {}).get("player")
        if not isinstance(player_entry, list) or not player_entry:
            continue
        attributes = player_entry[0]
        if isinstance(attributes, list):
            for element in attributes:
                if isinstance(element, dict) and "editorial_player_key" in element:
                    keys.append(str(element["editorial_player_key"]))
                    break
        elif isinstance(attributes, dict) and "editorial_player_key" in attributes:
            keys.append(str(attributes["editorial_player_key"]))
    return keys


def _extract_free_agent_player_keys(free_agents_payload: dict[str, Any]) -> list[str]:
    league = free_agents_payload.get("fantasy_content", {}).get("league")
    if not isinstance(league, list) or len(league) < 2:
        return []
    players_container = league[1].get("players")
    if not isinstance(players_container, dict):
        return []
    keys: list[str] = []
    for index, entry in players_container.items():
        if index == "count":
            continue
        player_data = entry.get("player") if isinstance(entry, dict) else None
        if not isinstance(player_data, list) or not player_data:
            continue
        attributes = player_data[0]
        if isinstance(attributes, list):
            for element in attributes:
                if isinstance(element, dict) and "editorial_player_key" in element:
                    keys.append(str(element["editorial_player_key"]))
                    break
    return keys


def _load_fixtures(fixtures_dir: Path) -> dict[str, Any]:
    base = fixtures_dir
    roster_path = base / "team_roster_current.json"
    scoreboard_path = base / "league_scoreboard_week8.json"
    player_stats_path = base / "player_stats_week8.json"
    season_stats_path = base / "player_stats_season.json"
    settings_path = base / "league_settings.json"
    free_agents_path = base / "free_agents.json"
    free_agent_stats_path = base / "free_agent_player_stats.json"

    try:
        roster = json.loads(roster_path.read_text(encoding="utf-8"))
        scoreboard = json.loads(scoreboard_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing fixture file: {exc.filename}") from exc

    player_stats = None
    if player_stats_path.exists():
        player_stats = json.loads(player_stats_path.read_text(encoding="utf-8"))
    season_player_stats = None
    if season_stats_path.exists():
        season_player_stats = json.loads(season_stats_path.read_text(encoding="utf-8"))

    league_settings = None
    if settings_path.exists():
        league_settings = json.loads(settings_path.read_text(encoding="utf-8"))

    free_agents = None
    if free_agents_path.exists():
        free_agents = json.loads(free_agents_path.read_text(encoding="utf-8"))
    free_agent_stats = None
    if free_agent_stats_path.exists():
        free_agent_stats = json.loads(free_agent_stats_path.read_text(encoding="utf-8"))

    return {
        "roster": roster,
        "scoreboard": scoreboard,
        "player_stats": player_stats,
        "season_player_stats": season_player_stats,
        "league_settings": league_settings,
        "free_agents": free_agents,
        "free_agent_player_stats": free_agent_stats,
    }


if __name__ == "__main__":
    raise SystemExit(main())
