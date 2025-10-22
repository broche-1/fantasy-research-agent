"""Compute insights from Yahoo Fantasy Football data snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


class MetricsError(RuntimeError):
    """Raised when weekly insights cannot be generated."""


@dataclass
class PlayerPerformance:
    """Normalized representation of a roster entry for analysis."""

    order: int
    player_key: str
    editorial_player_key: Optional[str]
    name: str
    position: Optional[str]
    slot: str
    is_flex: bool
    points: Optional[float]
    projected_points: Optional[float]
    eligible_positions: List[str] = field(default_factory=list)
    bye_week: Optional[int] = None

    @property
    def is_starter(self) -> bool:
        """Return True when the player occupies an active lineup slot."""
        return self.slot not in {"BN", "BENCH", "IR", "N/A", "NA"}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON-friendly output."""
        return {
            "player_key": self.player_key,
            "editorial_player_key": self.editorial_player_key,
            "name": self.name,
            "position": self.position,
            "slot": self.slot,
            "is_flex": self.is_flex,
            "points": self.points,
            "projected_points": self.projected_points,
        "eligible_positions": self.eligible_positions,
        "bye_week": self.bye_week,
    }

    def to_brief(self) -> Dict[str, Any]:
        """Compact serialization for recommendation output."""
        return {
            "name": self.name,
            "position": self.position,
            "slot": self.slot,
            "projected_points": self.projected_points,
        }


def summarize_week(week_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build a structured insight bundle for a single scoring week.

    Parameters
    ----------
    week_data:
        Expected keys:
            - ``roster``: Yahoo API payload from team roster endpoint.
            - ``scoreboard``: Yahoo API payload from league scoreboard endpoint.
        Optional keys:
            - ``team_key``: Preferred team key override (defaults to roster value).
            - ``player_stats``: Yahoo players stats payload for the week.
            - ``stat_modifiers``: Mapping of stat_id -> multiplier for fantasy points.

    Returns
    -------
    dict
        Dictionary containing matchup summary, lineup breakdown, and derived insights.
    """

    try:
        roster_payload = week_data["roster"]
        scoreboard_payload = week_data["scoreboard"]
    except KeyError as exc:
        missing = exc.args[0]
        raise MetricsError(f"Missing required week data key: {missing}") from exc

    stat_modifiers = _resolve_stat_modifiers(
        week_data.get("stat_modifiers"),
        week_data.get("league_settings"),
    )
    player_stats_payload = week_data.get("player_stats")
    season_player_stats_payload = week_data.get("season_player_stats")
    free_agents_payload = week_data.get("free_agents")
    free_agent_player_stats_payload = week_data.get("free_agent_player_stats")

    week_points_lookup = _build_player_points_lookup(player_stats_payload, stat_modifiers)
    season_points_lookup = _build_player_points_lookup(
        season_player_stats_payload,
        stat_modifiers,
        per_game=True,
    )
    free_agent_points_lookup = _build_player_points_lookup(
        free_agent_player_stats_payload,
        stat_modifiers,
        per_game=True,
    )

    roster_summary = _parse_roster(roster_payload, week_points_lookup, season_points_lookup)
    team_key = week_data.get("team_key") or roster_summary["team_key"]

    matchup = _find_matchup(scoreboard_payload, team_key)
    matchup_summary = _build_matchup_summary(matchup, team_key)

    players: List[PlayerPerformance] = roster_summary["players"]
    week_number = roster_summary["week"] or matchup.get("week")

    if week_number is not None:
        _apply_bye_week_overrides(players, int(week_number))

    requirements = _extract_roster_requirements(week_data.get("league_settings"))
    if requirements:
        _ensure_required_slots(players, requirements)

    lineup_section = _build_lineup_section(players, requirements)
    efficiency = _compute_efficiency(players)
    bench_review = _compute_bench_review(players)
    waiver_watch = _build_waiver_watch(matchup_summary)
    bench_moves = _suggest_bench_swaps(players)
    free_agent_targets = _build_free_agent_targets(
        free_agents_payload,
        free_agent_points_lookup,
    )

    week_number = roster_summary["week"] or matchup.get("week")

    return {
        "week": week_number,
        "team_key": _normalize_team_key(team_key),
        "team_name": roster_summary["team_name"],
        "matchup": matchup_summary,
        "lineup": lineup_section,
        "lineup_efficiency": efficiency,
        "bench_review": bench_review,
        "waiver_watch": waiver_watch,
        "bench_recommendations": bench_moves,
        "free_agent_targets": free_agent_targets,
        "projection_context": {
            "source": "derived",
            "description": "Projected points are computed from season stats per game using league scoring modifiers. Yahoo matchup projections shown above come directly from the API.",
        },
    }


# ---------------------------------------------------------------------------
# Roster parsing helpers
# ---------------------------------------------------------------------------

def _parse_roster(
    roster_payload: Dict[str, Any],
    week_points_lookup: Dict[str, Optional[float]],
    season_points_lookup: Dict[str, Optional[float]],
) -> Dict[str, Any]:
    team_section = _require_key(roster_payload, ["fantasy_content", "team"])
    if not isinstance(team_section, list) or len(team_section) < 2:
        raise MetricsError("Unexpected roster payload format: missing team section.")

    team_meta = team_section[0]
    roster_block = _find_dict(team_section, "roster")
    if not roster_block:
        raise MetricsError("Roster payload missing roster block.")

    players_container = _require_key(roster_block, ["0", "players"])

    players: List[PlayerPerformance] = []
    count = int(players_container.get("count", 0))
    for index in range(count):
        entry = players_container.get(str(index))
        if not entry or "player" not in entry:
            continue
        player_info = entry["player"]
        if not isinstance(player_info, list) or not player_info:
            continue

        attributes = player_info[0]
        if not isinstance(attributes, list):
            continue

        meta = _parse_player_metadata(attributes)
        player_key = meta.get("player_key")
        editorial_key = meta.get("editorial_key")
        name = meta.get("name")
        position = meta.get("position")
        eligible_positions = meta.get("eligible_positions", [])
        bye_week = meta.get("bye_week")

        slot_info = _find_dict(player_info, "selected_position") or []
        slot = _find_in_list(slot_info, "position") or "BN"
        is_flex_raw = _find_in_list(slot_info, "is_flex")
        is_flex = bool(int(is_flex_raw)) if isinstance(is_flex_raw, (int, str)) and str(is_flex_raw).isdigit() else False

        direct_points, _ = _extract_player_points(player_info)

        points = direct_points
        if points is None:
            points = _lookup_points(week_points_lookup, player_key, editorial_key)

        projected_points = _lookup_points(season_points_lookup, player_key, editorial_key)
        players.append(
            PlayerPerformance(
                order=index,
                player_key=str(player_key) if player_key is not None else f"unknown-{index}",
                editorial_player_key=editorial_key,
                name=str(name) if name else "Unknown Player",
                position=position,
                slot=slot,
                is_flex=is_flex,
                points=points,
                projected_points=projected_points,
                eligible_positions=eligible_positions,
                bye_week=bye_week,
            )
        )

    team_key = _find_in_list(team_meta, "team_key")
    team_name = _find_in_list(team_meta, "name")
    week_raw = roster_block.get("week")
    week = int(week_raw) if isinstance(week_raw, (int, str)) and str(week_raw).isdigit() else None

    return {
        "team_key": team_key,
        "team_name": team_name,
        "week": week,
        "players": players,
    }


def _extract_player_points(player_info: Iterable[Any]) -> Tuple[Optional[float], Optional[float]]:
    """Return tuple of (actual_points, projected_points) if present within roster entry."""
    actual: Optional[float] = None
    projected: Optional[float] = None

    for node in player_info:
        if isinstance(node, dict):
            if "player_points" in node:
                total = node["player_points"].get("total")
                value = _safe_float(total)
                if value is not None:
                    actual = value
            if "player_projected_points" in node:
                total = node["player_projected_points"].get("total")
                value = _safe_float(total)
                if value is not None:
                    projected = value
        elif isinstance(node, list):
            for sub in node:
                if isinstance(sub, dict):
                    if "player_points" in sub and actual is None:
                        value = _safe_float(sub["player_points"].get("total"))
                        if value is not None:
                            actual = value
                    if "player_projected_points" in sub and projected is None:
                        value = _safe_float(sub["player_projected_points"].get("total"))
                        if value is not None:
                            projected = value
    return actual, projected


def _build_player_points_lookup(
    player_stats_payload: Optional[Dict[str, Any]],
    stat_modifiers: Optional[Dict[str, float]],
    *,
    per_game: bool = False,
    games_stat_id: str = "0",
) -> Dict[str, Optional[float]]:
    """Create lookup of player_key/editorial_player_key -> fantasy points."""
    if not player_stats_payload:
        return {}

    players_section = _require_key(player_stats_payload, ["fantasy_content", "players"])
    count = int(players_section.get("count", 0))
    lookup: Dict[str, Optional[float]] = {}

    for index in range(count):
        entry = players_section.get(str(index))
        if not entry or "player" not in entry:
            continue
        player_block = entry["player"]
        if not isinstance(player_block, list) or len(player_block) < 2:
            continue

        attributes = player_block[0]
        stats_dict = player_block[1].get("player_stats", {})
        stats_list = stats_dict.get("stats", []) if isinstance(stats_dict, dict) else []

        player_key = _find_in_list(attributes, "player_key")
        editorial_key = _find_in_list(attributes, "editorial_player_key")

        points = _extract_points_from_stats(stats_list, stat_modifiers)
        if per_game and points is not None:
            games_played = _extract_stat_value(stats_list, games_stat_id)
            if games_played and games_played > 0:
                points = points / games_played

        if player_key:
            lookup[player_key] = points
        if editorial_key:
            lookup[editorial_key] = points

    return lookup


def _extract_points_from_stats(
    stats_list: Iterable[Any],
    stat_modifiers: Optional[Dict[str, float]],
) -> Optional[float]:
    """Return fantasy points from player stats, falling back to stat modifiers."""
    total: Optional[float] = None
    for stat_entry in stats_list:
        stat = stat_entry.get("stat") if isinstance(stat_entry, dict) else None
        if not stat:
            continue
        stat_id = str(stat.get("stat_id"))
        value = _safe_float(stat.get("value"))
        if stat_id == "9001" and value is not None:
            return value
        if value is None:
            continue
        if stat_modifiers and stat_id in stat_modifiers:
            total = (total or 0.0) + value * stat_modifiers[stat_id]
    return total


def _extract_stat_value(stats_list: Iterable[Any], target_id: str) -> Optional[float]:
    for stat_entry in stats_list:
        stat = stat_entry.get("stat") if isinstance(stat_entry, dict) else None
        if not stat:
            continue
        stat_id = str(stat.get("stat_id"))
        if stat_id == target_id:
            return _safe_float(stat.get("value"))
    return None


# ---------------------------------------------------------------------------
# Matchup helpers
# ---------------------------------------------------------------------------

def _find_matchup(scoreboard_payload: Dict[str, Any], team_key: Optional[str]) -> Dict[str, Any]:
    """Return matchup entry for the target team."""
    if not team_key:
        raise MetricsError("Team key required to identify matchup.")

    normalized_target = _normalize_team_key(team_key)

    league_section = _require_key(scoreboard_payload, ["fantasy_content", "league"])
    scoreboard_section = _find_dict(league_section, "scoreboard")
    if not scoreboard_section:
        raise MetricsError("Scoreboard payload missing scoreboard data.")

    week_raw = scoreboard_section.get("week")
    matchups_container = _require_key(scoreboard_section, ["0", "matchups"])
    matchup_count = int(matchups_container.get("count", 0))

    for index in range(matchup_count):
        matchup = matchups_container.get(str(index), {}).get("matchup")
        if not matchup:
            continue

        teams_container = _require_key(matchup, ["0", "teams"])
        teams_count = int(teams_container.get("count", 0))
        teams: List[Dict[str, Any]] = []

        for team_idx in range(teams_count):
            team_entry = teams_container.get(str(team_idx), {}).get("team")
            if not team_entry or len(team_entry) < 2:
                continue
            meta, stats = team_entry

            key = _find_in_list(meta, "team_key")
            team_normalized = _normalize_team_key(key)
            name = _find_in_list(meta, "name")
            points = _safe_float(_require_key(stats, ["team_points", "total"]))
            projected = _safe_float(_require_key(stats, ["team_projected_points", "total"]))
            win_probability = _safe_float(stats.get("win_probability"))

            teams.append(
                {
                    "team_key": key,
                    "team_key_normalized": team_normalized,
                    "name": name,
                    "points": points,
                    "projected_points": projected,
                    "win_probability": win_probability,
                }
            )

        for team_entry in teams:
            if team_entry["team_key_normalized"] == normalized_target:
                return {
                    "week": int(week_raw) if isinstance(week_raw, (int, str)) and str(week_raw).isdigit() else None,
                    "status": matchup.get("status"),
                    "is_playoffs": matchup.get("is_playoffs") == "1",
                    "teams": teams,
                }

    raise MetricsError(f"No matchup found for team key: {team_key}")


def _build_matchup_summary(matchup: Dict[str, Any], team_key: str) -> Dict[str, Any]:
    """Create digestible matchup dictionary."""
    normalized_target = _normalize_team_key(team_key)
    teams = matchup.get("teams", [])
    if len(teams) != 2:
        return {
            "status": matchup.get("status"),
            "result": "unknown",
            "detail": "Matchup data unavailable.",
            "teams": teams,
        }

    team_entry = None
    opponent_entry = None
    for entry in teams:
        if entry.get("team_key_normalized") == normalized_target:
            team_entry = entry
        else:
            opponent_entry = entry

    if not team_entry or not opponent_entry:
        raise MetricsError("Failed to identify both teams in matchup summary.")

    status = matchup.get("status") or "unknown"
    team_points = team_entry.get("points") or 0.0
    opponent_points = opponent_entry.get("points") or 0.0

    if status == "postevent":
        if team_points > opponent_points:
            result = "win"
        elif team_points < opponent_points:
            result = "loss"
        else:
            result = "tie"
    elif status in {"midevent", "live"}:
        result = "in_progress"
    else:
        result = "pending"

    return {
        "week": matchup.get("week"),
        "status": status,
        "result": result,
        "team": {
            "key": team_entry.get("team_key"),
            "name": team_entry.get("name"),
            "points": team_points,
            "projected_points": team_entry.get("projected_points"),
            "win_probability": team_entry.get("win_probability"),
        },
        "opponent": {
            "key": opponent_entry.get("team_key"),
            "name": opponent_entry.get("name"),
            "points": opponent_points,
            "projected_points": opponent_entry.get("projected_points"),
            "win_probability": opponent_entry.get("win_probability"),
        },
    }


# ---------------------------------------------------------------------------
# Insight builders
# ---------------------------------------------------------------------------

def _build_lineup_section(
    players: List[PlayerPerformance],
    requirements: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    starters = [player for player in players if player.is_starter]
    bench = [player for player in players if player.slot == "BN"]
    injured_reserve = [player for player in players if player.slot == "IR"]

    def serialize(items: Iterable[PlayerPerformance]) -> List[Dict[str, Any]]:
        return [player.to_dict() for player in sorted(items, key=lambda p: p.order)]

    return {
        "starters": serialize(starters),
        "bench": serialize(bench),
        "injured_reserve": serialize(injured_reserve),
        "totals": {
            "starter_count": len(starters),
            "bench_count": len(bench),
            "ir_count": len(injured_reserve),
            "player_count": len(players),
        },
    }


def _compute_efficiency(players: List[PlayerPerformance]) -> Dict[str, Any]:
    starter_points = [p.points for p in players if p.is_starter and p.points is not None]
    bench_points = [p.points for p in players if p.slot == "BN" and p.points is not None]
    starter_projected = [p.projected_points for p in players if p.is_starter and p.projected_points is not None]
    bench_projected = [p.projected_points for p in players if p.slot == "BN" and p.projected_points is not None]

    if not starter_points and not bench_points:
        return {
            "data_available": False,
            "actual_points": None,
            "optimal_points": None,
            "points_left_on_bench": None,
            "notes": "Player-level fantasy points not provided in inputs.",
            "projected_points": sum(starter_projected) if starter_projected else None,
            "bench_projected_points": sum(bench_projected) if bench_projected else None,
        }

    actual = sum(starter_points)

    # Simple best-case swap: replace the lowest starter score with higher bench scores.
    optimal_candidates = starter_points[:]
    for bench_value in sorted(bench_points, reverse=True):
        if not optimal_candidates:
            break
        lowest = min(optimal_candidates)
        if bench_value > lowest:
            optimal_candidates.remove(lowest)
            optimal_candidates.append(bench_value)

    optimal = sum(optimal_candidates)
    points_left = max(0.0, optimal - actual)

    projected_actual = round(sum(starter_projected), 2) if starter_projected else None
    bench_projected_total = round(sum(bench_projected), 2) if bench_projected else None

    projected_optimal_total, projected_gain = _compute_projected_optimal(players)

    return {
        "data_available": True,
        "actual_points": round(actual, 2),
        "optimal_points": round(optimal, 2),
        "points_left_on_bench": round(points_left, 2),
        "notes": "Bench comparison assumes identical positional eligibility.",
        "projected_points": projected_actual,
        "bench_projected_points": bench_projected_total,
        "projected_optimal_points": projected_optimal_total,
        "projected_points_gain": projected_gain,
    }


def _compute_bench_review(players: List[PlayerPerformance]) -> Dict[str, Any]:
    starter_points = [p.points for p in players if p.is_starter and p.points is not None]
    bench_points = [p.points for p in players if p.slot == "BN" and p.points is not None]
    starter_projected = [p.projected_points for p in players if p.is_starter and p.projected_points is not None]
    bench_projected = [p.projected_points for p in players if p.slot == "BN" and p.projected_points is not None]

    data_available = bool(starter_points or bench_points)
    starter_projected_total = round(sum(starter_projected), 2) if starter_projected else None
    bench_projected_total = round(sum(bench_projected), 2) if bench_projected else None

    return {
        "data_available": data_available,
        "starter_points": round(sum(starter_points), 2) if starter_points else None,
        "bench_points": round(sum(bench_points), 2) if bench_points else None,
        "starter_projected_points": starter_projected_total,
        "bench_projected_points": bench_projected_total,
        "starter_count": len([p for p in players if p.is_starter]),
        "bench_count": len([p for p in players if p.slot == "BN"]),
        "notes": None
        if data_available
        else "Bench review limited to roster counts; scoring data unavailable.",
    }


def _compute_projected_optimal(players: List[PlayerPerformance]) -> Tuple[Optional[float], Optional[float]]:
    starters = [p for p in players if p.is_starter and p.projected_points is not None]
    bench = [p for p in players if p.slot == "BN" and p.projected_points is not None]
    if not starters:
        return (None, None)

    current_total = sum(p.projected_points for p in starters if p.projected_points is not None)
    best_total = current_total

    for bench_player in bench:
        for starter in starters:
            if not starter.projected_points or not bench_player.projected_points:
                continue
            if not _positions_overlap(bench_player, starter):
                continue
            if bench_player.projected_points <= starter.projected_points:
                continue
            new_total = current_total - starter.projected_points + bench_player.projected_points
            if new_total > best_total:
                best_total = new_total

    gain = max(0.0, best_total - current_total)
    return (round(best_total, 2), round(gain, 2))


def _build_waiver_watch(matchup: Dict[str, Any]) -> List[Dict[str, Any]]:
    team_info = matchup.get("team", {})
    win_probability = team_info.get("win_probability")
    recommendations: List[Dict[str, Any]] = []

    if isinstance(win_probability, (int, float)) and win_probability < 0.5:
        recommendations.append(
            {
                "type": "win_probability",
                "message": (
                    f"Win probability sits at {win_probability:.0%}. "
                    "Consider waiver moves or lineup tweaks to swing the matchup."
                ),
            }
        )

    return recommendations


def _suggest_bench_swaps(players: List[PlayerPerformance], threshold: float = 1.5) -> List[Dict[str, Any]]:
    starters = [p for p in players if p.is_starter and (p.projected_points or 0) > 0]
    bench = [p for p in players if p.slot == "BN" and (p.projected_points or 0) > 0]
    if not starters or not bench:
        return []

    suggestions: List[Dict[str, Any]] = []
    used_starters: set[str] = set()

    for bench_player in sorted(bench, key=lambda p: p.projected_points or 0.0, reverse=True):
        best_candidate: Optional[PlayerPerformance] = None
        best_diff = threshold
        for starter in starters:
            starter_id = starter.player_key
            if starter_id in used_starters:
                continue
            if not starter.projected_points:
                continue
            if not _positions_overlap(bench_player, starter):
                continue
            diff = (bench_player.projected_points or 0) - starter.projected_points
            if diff >= threshold and diff > best_diff:
                best_candidate = starter
                best_diff = diff
        if best_candidate:
            used_starters.add(best_candidate.player_key)
            suggestions.append(
                {
                    "bench_player": bench_player.to_brief(),
                    "starter": best_candidate.to_brief(),
                    "projected_difference": round(best_diff, 2),
                }
            )
    return suggestions[:3]


def _build_free_agent_targets(
    free_agents_payload: Optional[Dict[str, Any]],
    projection_lookup: Dict[str, Optional[float]],
    *,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    if not free_agents_payload:
        return []

    league = free_agents_payload.get("fantasy_content", {}).get("league")
    if not isinstance(league, list) or len(league) < 2:
        return []
    players_container = league[1].get("players")
    if not isinstance(players_container, dict):
        return []

    candidates: List[Dict[str, Any]] = []
    for index, entry in players_container.items():
        if index == "count":
            continue
        player_entry = entry.get("player") if isinstance(entry, dict) else None
        if not isinstance(player_entry, list) or not player_entry:
            continue
        attributes = player_entry[0]
        if not isinstance(attributes, list):
            continue
        meta = _parse_player_metadata(attributes)
        editorial_key = meta.get("editorial_key")
        projected = _lookup_points(projection_lookup, meta.get("player_key"), editorial_key)
        if not projected or projected <= 0:
            continue
        candidates.append(
            {
                "name": meta.get("name"),
                "position": meta.get("position"),
                "team": meta.get("team"),
                "projected_points": round(projected, 2),
            }
        )

    candidates.sort(key=lambda item: item["projected_points"], reverse=True)
    return candidates[:max_results]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _normalize_team_key(team_key: Optional[str]) -> Optional[str]:
    if not team_key:
        return team_key
    parts = str(team_key).split(".")
    if len(parts) >= 4:
        return ".".join(parts[-4:])
    return team_key


def _lookup_points(
    lookup: Dict[str, Optional[float]],
    player_key: Optional[str],
    editorial_key: Optional[str],
) -> Optional[float]:
    if editorial_key and editorial_key in lookup:
        return lookup[editorial_key]
    if player_key and player_key in lookup:
        return lookup[player_key]
    return None


def _extract_eligible_positions(attributes: Iterable[Any]) -> List[str]:
    for item in attributes:
        if isinstance(item, dict) and "eligible_positions" in item:
            positions = item["eligible_positions"]
            if isinstance(positions, list):
                return [entry.get("position") for entry in positions if isinstance(entry, dict) and entry.get("position")]
    return []


def _parse_player_metadata(attributes: Iterable[Any]) -> Dict[str, Any]:
    player_key = _find_in_list(attributes, "player_key")
    editorial_key = _find_in_list(attributes, "editorial_player_key")
    name_block = _find_in_list(attributes, "name")
    name = name_block.get("full") if isinstance(name_block, dict) else name_block
    position = _find_in_list(attributes, "primary_position") or _find_in_list(attributes, "display_position")
    team = _find_in_list(attributes, "editorial_team_abbr")
    eligible_positions = _extract_eligible_positions(attributes)
    bye_week = None
    bye_info = _find_in_list(attributes, "bye_weeks")
    if isinstance(bye_info, dict):
        bye_value = bye_info.get("week")
        if isinstance(bye_value, str) and bye_value.isdigit():
            bye_week = int(bye_value)
        elif isinstance(bye_value, int):
            bye_week = bye_value
    return {
        "player_key": player_key,
        "editorial_key": editorial_key,
        "name": name,
        "position": position,
        "team": team,
        "eligible_positions": eligible_positions,
        "bye_week": bye_week,
    }


def _positions_overlap(bench_player: PlayerPerformance, starter: PlayerPerformance) -> bool:
    primary = bench_player.position
    starter_slot = starter.slot
    starter_position = starter.position

    if primary and starter_position and primary == starter_position:
        return True

    flex_positions = {"RB", "WR", "TE"}
    flex_slots = {"W/R/T", "W/T", "W/R"}
    if primary in flex_positions and starter_slot in flex_slots:
        return True

    # Allow using eligible positions (including DEF/K etc.)
    if starter_slot == starter_position and bench_player.eligible_positions:
        return starter_position in bench_player.eligible_positions

    return False


def _apply_bye_week_overrides(players: List[PlayerPerformance], week: int) -> None:
    for player in players:
        if player.bye_week == week:
            if player.projected_points is not None:
                player.projected_points = 0.0
            if player.points is not None:
                player.points = 0.0


def _extract_roster_requirements(league_settings_payload: Optional[Dict[str, Any]]) -> Dict[str, int]:
    if not league_settings_payload:
        return {}
    try:
        league_section = _require_key(league_settings_payload, ["fantasy_content", "league"])
    except MetricsError:
        return {}

    settings_section = _find_dict(league_section, "settings")
    if isinstance(settings_section, list):
        settings_dict = settings_section[0] if settings_section else {}
    elif isinstance(settings_section, dict):
        settings_dict = settings_section
    else:
        settings_dict = {}

    roster_positions = settings_dict.get("roster_positions")
    if not roster_positions:
        return {}

    positions_list: List[Dict[str, Any]] = []
    if isinstance(roster_positions, list):
        positions_list = roster_positions
    elif isinstance(roster_positions, dict):
        positions_list = roster_positions.get("roster_position", [])  # type: ignore[assignment]

    requirements: Dict[str, int] = {}
    for entry in positions_list:
        roster_position = entry.get("roster_position") if isinstance(entry, dict) else entry
        if not isinstance(roster_position, dict):
            continue
        if str(roster_position.get("is_starting_position")) != "1":
            continue
        position = roster_position.get("position")
        if not position or position in {"BN", "IR"}:
            continue
        try:
            count = int(roster_position.get("count", 0))
        except (TypeError, ValueError):
            continue
        requirements[position] = count
    return requirements


def _ensure_required_slots(players: List[PlayerPerformance], requirements: Dict[str, int]) -> None:
    if not requirements:
        return
    max_order = max((player.order for player in players), default=0)
    for slot, required in requirements.items():
        current = sum(1 for player in players if player.is_starter and player.slot == slot)
        missing = required - current
        for _ in range(max(0, missing)):
            max_order += 1
            players.append(_create_placeholder_player(slot, max_order))


def _create_placeholder_player(slot: str, order: int) -> PlayerPerformance:
    is_flex = slot in {"W/R/T", "W/R", "W/T"}
    return PlayerPerformance(
        order=order,
        player_key=f"placeholder-{slot}-{order}",
        editorial_player_key=None,
        name="Open Slot",
        position=slot,
        slot=slot,
        is_flex=is_flex,
        points=0.0,
        projected_points=0.0,
        eligible_positions=[slot],
        bye_week=None,
    )


def _resolve_stat_modifiers(
    stat_modifiers: Optional[Any],
    settings_payload: Optional[Dict[str, Any]],
) -> Optional[Dict[str, float]]:
    """Return mapping of stat_id -> fantasy multiplier from provided inputs."""
    modifiers = _stat_modifiers_from_generic(stat_modifiers)
    if modifiers:
        return modifiers
    if settings_payload:
        modifiers = _stat_modifiers_from_settings(settings_payload)
    return modifiers if modifiers else None


def _stat_modifiers_from_generic(raw: Optional[Any]) -> Dict[str, float]:
    if not raw:
        return {}
    modifiers: Dict[str, float] = {}

    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for entry in raw:
            if isinstance(entry, dict):
                items.append(entry.items())
        # Flatten below by continuing logic
    else:
        return {}

    # When raw is list of dict with nested stat, treat specially.
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            stat = entry.get("stat", entry)
            if not isinstance(stat, dict):
                continue
            stat_id = stat.get("stat_id")
            value = _safe_float(stat.get("value"))
            if stat_id is None or value is None:
                continue
            modifiers[str(stat_id)] = value
        return modifiers

    for key, value in items:  # type: ignore[arg-type]
        stat_id = str(key)
        multiplier = _safe_float(value)
        if multiplier is None:
            continue
        modifiers[stat_id] = multiplier
    return modifiers


def _stat_modifiers_from_settings(settings_payload: Dict[str, Any]) -> Dict[str, float]:
    """Extract stat modifiers from the league settings payload."""
    try:
        league_section = _require_key(settings_payload, ["fantasy_content", "league"])
    except MetricsError:
        return {}

    settings_list = _find_dict(league_section, "settings")
    if isinstance(settings_list, list):
        settings_dict = settings_list[0] if settings_list else {}
    elif isinstance(settings_list, dict):
        settings_dict = settings_list
    else:
        settings_dict = {}

    modifiers_section = {}
    if isinstance(settings_dict, dict):
        modifiers_section = settings_dict.get("stat_modifiers", {})

    stats_list = modifiers_section.get("stats") if isinstance(modifiers_section, dict) else None
    if isinstance(stats_list, list):
        return _stat_modifiers_from_generic(stats_list)
    return {}


def _find_dict(items: Iterable[Any], target_key: str) -> Optional[Dict[str, Any]]:
    for item in items:
        if isinstance(item, dict) and target_key in item:
            return item[target_key]
    return None


def _find_in_list(items: Iterable[Any], target_key: str) -> Any:
    for item in items:
        if isinstance(item, dict) and target_key in item:
            return item[target_key]
    return None


def _require_key(container: Dict[str, Any], path: List[str]) -> Any:
    current: Any = container
    for key in path:
        if not isinstance(current, dict) or key not in current:
            raise MetricsError(f"Expected key {'/'.join(path)} in payload.")
        current = current[key]
    return current


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
