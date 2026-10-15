"""Clock / time-management analytics derived from PGN %clk data."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Game, GameMove

TIME_PRESSURE_SECONDS = 15


def _increment(time_control: Optional[str]) -> float:
    if not time_control or "+" not in time_control:
        return 0.0
    try:
        return float(time_control.split("+")[1])
    except (ValueError, IndexError):
        return 0.0


def clock_report(session: Session, user_id: int, days: Optional[int] = None) -> dict:
    q = select(Game).where(Game.user_id == user_id, Game.has_clock_data == True)  # noqa: E712
    if days:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        q = q.where(Game.end_time >= since)
    games = list(session.scalars(q))
    if not games:
        return {"has_data": False, "note": "No games with clock data were found."}

    game_ids = [g.id for g in games]
    gmap = {g.id: g for g in games}
    moves = session.scalars(
        select(GameMove).where(GameMove.game_id.in_(game_ids)).order_by(GameMove.game_id, GameMove.ply)
    ).all()

    per_player_think: list[float] = []
    by_phase: dict[str, list[float]] = defaultdict(list)
    errors_low_time = 0
    time_forfeits = 0
    acc_final_seconds: list[float] = []
    with_inc = without_inc = 0

    prev_clock: dict[tuple[int, str], float] = {}
    for g in games:
        if (g.termination or "").lower().find("time") >= 0 or "forfeit" in (g.termination or "").lower():
            time_forfeits += 1
        if _increment(g.time_control) > 0:
            with_inc += 1
        elif g.has_clock_data:
            without_inc += 1

    for mv in moves:
        g = gmap.get(mv.game_id)
        if g is None or g.player_color is None or mv.color != g.player_color:
            continue
        if mv.clock_seconds is None:
            continue

        # Thinking time = previous remaining (same player) - current remaining + increment.
        key = (mv.game_id, mv.color)
        prev = prev_clock.get(key)
        inc = _increment(g.time_control)
        if prev is not None:
            think = max(0.0, prev - mv.clock_seconds + inc)
            mv.think_seconds = think
            per_player_think.append(think)
            phase = "opening" if mv.move_number <= 10 else ("endgame" if mv.move_number > 30 else "middlegame")
            by_phase[phase].append(think)
            if mv.classification in ("blunder", "mistake") and mv.clock_seconds <= TIME_PRESSURE_SECONDS:
                errors_low_time += 1
        prev_clock[key] = mv.clock_seconds
        if mv.clock_seconds <= TIME_PRESSURE_SECONDS:
            acc_final_seconds.append(mv.clock_seconds)

    session.commit()

    def avg(xs: list[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "has_data": True,
        "games_with_clock": len(games),
        "avg_think_seconds": avg(per_player_think),
        "by_phase": {k: avg(v) for k, v in by_phase.items()},
        "errors_under_pressure": errors_low_time,
        "time_pressure_threshold": TIME_PRESSURE_SECONDS,
        "time_forfeits": time_forfeits,
        "games_with_increment": with_inc,
        "games_without_increment": without_inc,
        "note": "Thinking times are derived from PGN clock stamps; games without clock data are excluded.",
    }
