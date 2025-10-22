"""Tests for weekly metrics summarization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_processor.metrics import MetricsError, summarize_week


def load_fixture(name: str) -> dict:
    """Load JSON fixture from fixtures directory."""
    path = Path("fixtures") / name
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def week_payload() -> dict:
    """Representative week snapshot assembled from Yahoo API fixtures."""
    return {
        "roster": load_fixture("team_roster_current.json"),
        "scoreboard": load_fixture("league_scoreboard_week8.json"),
        "player_stats": load_fixture("player_stats_week8.json"),
        "season_player_stats": load_fixture("player_stats_season.json"),
        "league_settings": load_fixture("league_settings.json"),
        "free_agents": load_fixture("free_agents.json"),
        "free_agent_player_stats": load_fixture("free_agent_player_stats.json"),
    }


def test_summarize_week_returns_expected_structure(week_payload: dict) -> None:
    summary = summarize_week(week_payload)

    assert summary["week"] == 8
    assert summary["team_key"] == "l.303321.t.8"
    assert summary["team_name"] == "Ur gunna Drake Maye cum"

    matchup = summary["matchup"]
    assert matchup["status"] == "midevent"
    assert matchup["team"]["name"] == "Ur gunna Drake Maye cum"
    assert matchup["opponent"]["name"] == "C. Bass"
    assert matchup["team"]["projected_points"] == pytest.approx(73.62)

    lineup = summary["lineup"]
    assert lineup["totals"]["starter_count"] == 9
    assert lineup["totals"]["bench_count"] == 7
    assert lineup["totals"]["ir_count"] == 0
    assert lineup["starters"][0]["slot"] == "QB"
    assert lineup["starters"][0]["projected_points"] is not None

    efficiency = summary["lineup_efficiency"]
    assert efficiency["data_available"] is True
    assert efficiency["actual_points"] == pytest.approx(0.0)
    assert efficiency["optimal_points"] == pytest.approx(0.0)
    assert efficiency["points_left_on_bench"] == pytest.approx(0.0)
    assert efficiency["projected_points"] is not None
    assert efficiency["projected_optimal_points"] is not None
    assert efficiency["projected_points_gain"] is not None

    bench_review = summary["bench_review"]
    assert bench_review["data_available"] is True
    assert bench_review["starter_count"] == 9
    assert bench_review["bench_count"] == 7
    assert bench_review["starter_points"] == pytest.approx(0.0)
    assert bench_review["bench_points"] == pytest.approx(0.0)
    assert bench_review["starter_projected_points"] is not None
    assert bench_review["bench_projected_points"] is not None

    waiver_watch = summary["waiver_watch"]
    assert waiver_watch, "Expected waiver watch recommendations when underdog."
    assert "win probability" in waiver_watch[0]["message"].lower()

    assert "bench_recommendations" in summary
    assert "free_agent_targets" in summary
    if summary["bench_recommendations"]:
        first_move = summary["bench_recommendations"][0]
        assert first_move["projected_difference"] >= 0
    if summary["free_agent_targets"]:
        first_agent = summary["free_agent_targets"][0]
        assert first_agent["projected_points"] is not None


def test_missing_scoreboard_raises_error(week_payload: dict) -> None:
    minimal = {"roster": week_payload["roster"]}
    with pytest.raises(MetricsError):
        summarize_week(minimal)
