#!/usr/bin/env python3
"""Refresh local fixtures and weekly reports from the Yahoo API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List

BASE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from data_fetcher.yahoo_client import YahooClient
from data_processor.metrics import summarize_week
from report_generator.markdown import render_report
from main import _extract_editorial_player_keys, _infer_current_week


def dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def collect_free_agent_keys(payload: dict) -> List[str]:
    league = payload.get("fantasy_content", {}).get("league")
    if not isinstance(league, list) or len(league) < 2:
        return []
    players_container = league[1].get("players")
    if not isinstance(players_container, dict):
        return []

    keys: List[str] = []
    for idx, entry in players_container.items():
        if idx == "count":
            continue
        player_entry = entry.get("player") if isinstance(entry, dict) else None
        if not isinstance(player_entry, list) or not player_entry:
            continue
        attributes = player_entry[0]
        if not isinstance(attributes, list):
            continue
        for element in attributes:
            if isinstance(element, dict) and "editorial_player_key" in element:
                keys.append(str(element["editorial_player_key"]))
                break
    return keys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh local fixtures using live Yahoo data.")
    parser.add_argument("--week", type=int, help="Week to refresh (defaults to league current week).")
    parser.add_argument("--free-agent-count", type=int, default=15, help="Number of available players to capture.")
    parser.add_argument("--fixtures-dir", type=Path, default=Path("fixtures"), help="Directory to write fixture JSON files.")
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"), help="Directory to write Markdown/JSON reports.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = YahooClient.from_env()

    week = args.week or _infer_current_week(client, None)

    roster = client.fetch_team_roster(week=week, use_cache=False)
    scoreboard = client.fetch_matchup_results(week=week, use_cache=False)
    league_settings = client.fetch_league_settings(use_cache=False)
    league_metadata = client.fetch_league_metadata()

    player_keys = _extract_editorial_player_keys(roster)
    player_stats_week = client.fetch_player_stats(player_keys, week=week, use_cache=False) if player_keys else {}
    player_stats_season = client.fetch_player_stats(player_keys, stat_type="season", use_cache=False) if player_keys else {}

    free_agents = client.fetch_free_agents(week=week, count=args.free_agent_count, use_cache=False)
    free_agent_keys = collect_free_agent_keys(free_agents)
    free_agent_stats = (
        client.fetch_player_stats(free_agent_keys, stat_type="season", use_cache=False)
        if free_agent_keys
        else {}
    )

    fixtures_dir = args.fixtures_dir
    dump_json(fixtures_dir / "team_roster_current.json", roster)
    dump_json(fixtures_dir / f"league_scoreboard_week{week}.json", scoreboard)
    dump_json(fixtures_dir / "league_settings.json", league_settings)
    dump_json(fixtures_dir / "league_metadata.json", league_metadata)
    dump_json(fixtures_dir / f"player_stats_week{week}.json", player_stats_week)
    dump_json(fixtures_dir / "player_stats_season.json", player_stats_season)
    dump_json(fixtures_dir / "free_agents.json", free_agents)
    dump_json(fixtures_dir / "free_agent_player_stats.json", free_agent_stats)

    summary = summarize_week(
        {
            "roster": roster,
            "scoreboard": scoreboard,
            "player_stats": player_stats_week,
            "season_player_stats": player_stats_season,
            "league_settings": league_settings,
            "free_agents": free_agents,
            "free_agent_player_stats": free_agent_stats,
        }
    )
    reports_dir = args.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    dump_json(reports_dir / f"week_{week}_summary.json", summary)
    reports_dir.joinpath(f"week_{week}_report.md").write_text(render_report(summary), encoding="utf-8")

    print(f"Fixtures and reports refreshed for week {week}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
