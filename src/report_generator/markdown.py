"""Generate Markdown output for weekly reports."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List


def render_report(insights: Dict[str, Any]) -> str:
    """Return Markdown document for the given insights."""
    week = insights.get("week", "?")
    team_name = insights.get("team_name", "Your Team")
    matchup = insights.get("matchup", {})
    lineup = insights.get("lineup", {})
    efficiency = insights.get("lineup_efficiency", {})
    bench_review = insights.get("bench_review", {})
    waiver_watch = insights.get("waiver_watch", [])
    bench_moves = insights.get("bench_recommendations", [])
    free_agent_targets = insights.get("free_agent_targets", [])
    projection_context = insights.get("projection_context", {})

    opponent = matchup.get("opponent", {})
    team = matchup.get("team", {})

    lines: List[str] = []
    lines.append(f"# Week {week} Report — {team_name}")
    lines.append("")
    lines.append(_build_matchup_overview(matchup, team, opponent))
    lines.append("")
    lines.extend(_build_lineup_section(lineup))
    lines.append("")
    lines.extend(_build_efficiency_section(efficiency, bench_review))
    lines.append("")
    lines.extend(_build_bench_moves_section(bench_moves))
    lines.append("")
    lines.extend(_build_free_agent_section(free_agent_targets))
    lines.append("")
    lines.extend(_build_waiver_section(waiver_watch))
    if projection_context:
        lines.append("")
        lines.append(_build_projection_note(projection_context))
    return "\n".join(lines).strip() + "\n"


def _build_matchup_overview(
    matchup: Dict[str, Any],
    team: Dict[str, Any],
    opponent: Dict[str, Any],
) -> str:
    status = matchup.get("status", "unknown").replace("_", " ").title()
    result = matchup.get("result", "pending").replace("_", " ").title()
    team_points = _format_points(team.get("points"))
    opp_points = _format_points(opponent.get("points"))
    team_proj = _format_points(team.get("projected_points"))
    opp_proj = _format_points(opponent.get("projected_points"))
    team_wp = _format_percentage(team.get("win_probability"))
    opp_wp = _format_percentage(opponent.get("win_probability"))

    lines = [
        f"## Matchup Snapshot",
        "",
        f"| | {team.get('name', 'Team')} | {opponent.get('name', 'Opponent')} |",
        "| --- | ---: | ---: |",
        f"| Status | {status} | {result} |",
        f"| Points | {team_points} | {opp_points} |",
        f"| Projected | {team_proj} | {opp_proj} |",
        f"| Win Probability | {team_wp} | {opp_wp} |",
    ]
    return "\n".join(lines)


def _build_lineup_section(lineup: Dict[str, Any]) -> List[str]:
    starters = lineup.get("starters", [])
    bench = lineup.get("bench", [])
    injured = lineup.get("injured_reserve", [])
    totals = lineup.get("totals", {})

    lines = ["## Lineup Breakdown", ""]
    lines.append("### Starters")
    lines.extend(_render_player_table(starters))
    lines.append("")
    lines.append("### Bench")
    lines.extend(_render_player_table(bench))
    if injured:
        lines.append("")
        lines.append("### Injured Reserve")
        lines.extend(_render_player_table(injured))

    meta_line = (
        f"_Roster size: {totals.get('player_count', len(starters) + len(bench) + len(injured))} "
        f"(Starters {totals.get('starter_count', len(starters))}, "
        f"Bench {totals.get('bench_count', len(bench))}, "
        f"IR {totals.get('ir_count', len(injured))})_"
    )
    lines.append("")
    lines.append(meta_line)
    return lines


def _render_player_table(players: Iterable[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    lines.append("| Slot | Player | Pos | Proj | Points |")
    lines.append("| --- | --- | --- | ---: | ---: |")
    for player in players:
        slot = player.get("slot", "-")
        name = player.get("name", "Unknown")
        position = player.get("position", "-") or "-"
        points = _format_points(player.get("points"))
        projected = _format_points(player.get("projected_points"))
        lines.append(f"| {slot} | {name} | {position} | {projected} | {points} |")
    if len(lines) == 2:
        lines.append("| _No players_ |  |  |  |  |")
    return lines


def _build_efficiency_section(
    efficiency: Dict[str, Any],
    bench_review: Dict[str, Any],
) -> List[str]:
    lines = ["## Efficiency Check", ""]
    if not efficiency.get("data_available"):
        lines.append("Fantasy scoring totals unavailable; efficiency metrics omitted.")
    else:
        lines.append(
            f"- Actual points: **{_format_points(efficiency.get('actual_points'))}**"
        )
        lines.append(
            f"- Optimal lineup: **{_format_points(efficiency.get('optimal_points'))}** "
            f"(bench upside {_format_points(efficiency.get('points_left_on_bench'))})"
        )
        if efficiency.get("notes"):
            lines.append(f"- _{efficiency['notes']}_")
        projected_total = efficiency.get("projected_points")
        bench_projected = efficiency.get("bench_projected_points")
        if projected_total is not None:
            lines.append(
                f"- Projected totals: starters {_format_points(projected_total)}, bench {_format_points(bench_projected)}."
            )
        projected_optimal = efficiency.get("projected_optimal_points")
        projected_gain = efficiency.get("projected_points_gain")
        if projected_optimal is not None:
            lines.append(
                f"- Projected optimal lineup: **{_format_points(projected_optimal)}** "
                f"(gain {_format_points(projected_gain)} pts)."
            )

    lines.append("")
    if not bench_review.get("data_available"):
        lines.append("Bench overview: scoring data unavailable.")
    else:
        lines.append(
            f"Bench contributed {_format_points(bench_review.get('bench_points'))} across "
            f"{bench_review.get('bench_count', 0)} spots; starters produced "
            f"{_format_points(bench_review.get('starter_points'))}."
        )
        if bench_review.get("bench_projected_points") is not None and bench_review.get("starter_projected_points") is not None:
            lines.append(
                f"Projected totals: starters {_format_points(bench_review.get('starter_projected_points'))}, "
                f"bench {_format_points(bench_review.get('bench_projected_points'))}."
            )
    return lines


def _build_bench_moves_section(bench_moves: Iterable[Dict[str, Any]]) -> List[str]:
    lines = ["## Bench Moves", ""]
    moves = list(bench_moves)
    if not moves:
        lines.append("No obvious bench upgrades surfaced this week.")
        return lines

    for move in moves:
        bench_player = move.get("bench_player", {})
        starter = move.get("starter", {})
        diff = move.get("projected_difference")
        lines.append(
            f"- Start **{bench_player.get('name')}** ({bench_player.get('position')}) over "
            f"**{starter.get('name')}** ({starter.get('position')}), projected swing {diff:.2f} pts."
        )
    return lines


def _build_free_agent_section(free_agents: Iterable[Dict[str, Any]]) -> List[str]:
    lines = ["## Free-Agent Radar", ""]
    agents = list(free_agents)
    if not agents:
        lines.append("No high-upside free agents identified right now.")
        return lines

    lines.append("| Player | Pos | Team | Proj |")
    lines.append("| --- | --- | --- | ---: |")
    for agent in agents:
        lines.append(
            "| {name} | {position} | {team} | {proj} |".format(
                name=agent.get("name", "Unknown"),
                position=agent.get("position", "-"),
                team=agent.get("team", "-"),
                proj=_format_points(agent.get("projected_points")),
            )
        )
    return lines


def _build_waiver_section(waiver_watch: Iterable[Dict[str, Any]]) -> List[str]:
    lines = ["## Waiver Watch", ""]
    entries = list(waiver_watch)
    if not entries:
        lines.append("No immediate waiver recommendations this week.")
        return lines
    for entry in entries:
        message = entry.get("message", "").strip()
        if not message:
            continue
        lines.append(f"- {message}")
    if len(lines) == 2:
        lines.append("No immediate waiver recommendations this week.")
    return lines


def _build_projection_note(context: Dict[str, Any]) -> str:
    description = context.get("description") or "Projected points are derived from season performance." 
    return f"_Projection note: {description}_"


def _format_points(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def _format_percentage(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return str(value)
