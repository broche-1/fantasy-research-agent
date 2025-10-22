"""Tests for Markdown report rendering and CLI summary helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_processor.metrics import summarize_week
from report_generator.markdown import render_report
from src import main as cli_main


def load_fixture(name: str) -> dict:
    """Utility to load fixture JSON into Python structures."""
    path = Path("fixtures") / name
    return json.loads(path.read_text())


def build_summary() -> dict:
    """Assemble weekly insights using local fixtures."""
    payload = {
        "roster": load_fixture("team_roster_current.json"),
        "scoreboard": load_fixture("league_scoreboard_week8.json"),
        "player_stats": load_fixture("player_stats_week8.json"),
        "season_player_stats": load_fixture("player_stats_season.json"),
        "league_settings": load_fixture("league_settings.json"),
        "free_agents": load_fixture("free_agents.json"),
        "free_agent_player_stats": load_fixture("free_agent_player_stats.json"),
    }
    return summarize_week(payload)


def test_render_report_includes_core_sections() -> None:
    summary = build_summary()
    markdown = render_report(summary)

    assert markdown.startswith("# Week 8 Report — Ur gunna Drake Maye cum")
    assert "## Matchup Snapshot" in markdown
    assert "Ur gunna Drake Maye cum" in markdown
    assert "C. Bass" in markdown
    assert "## Lineup Breakdown" in markdown
    assert "| QB | Lamar Jackson" in markdown
    assert "| Slot | Player | Pos | Proj | Points |" in markdown
    assert "## Bench Moves" in markdown
    assert "## Free-Agent Radar" in markdown
    assert "## Waiver Watch" in markdown
    assert "Win probability sits at 30%" in markdown
    assert "Projected totals: starters" in markdown
    assert "Projected optimal lineup" in markdown
    assert "Projection note" in markdown


def test_summarize_week_command_uses_fixture_path() -> None:
    args = argparse.Namespace(
        week=None,
        team_key=None,
        league_key=None,
        no_cache=False,
        use_fixtures=True,
        fixtures_dir=Path("fixtures"),
        output=None,
        format="json",
        pretty=False,
    )

    summary = cli_main._summarize_week_command(None, args)  # type: ignore[arg-type]

    assert summary["team_name"] == "Ur gunna Drake Maye cum"
    assert summary["matchup"]["opponent"]["name"] == "C. Bass"
    assert "free_agent_targets" in summary
