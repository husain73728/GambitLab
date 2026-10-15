"""Aggregate statistics with a materialized cache (never recomputed per page load)."""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from typing import Any, Callable, Optional

import chess
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import AnalysisJob, Game, GameMove, StatCache, TacticalEvent

CACHE_VERSION = "v3"


def invalidate_stats(session: Session, user_id: int) -> None:
    session.execute(delete(StatCache).where(StatCache.user_id == user_id))
    session.commit()


def _cached(session: Session, user_id: int, key: str, compute: Callable[[], Any]) -> Any:
    key = f"{CACHE_VERSION}:{key}"
    row = session.scalar(
        select(StatCache).where(StatCache.user_id == user_id, StatCache.key == key)
    )
    if row is not None:
        return row.value
    value = compute()
    if row is None:
        session.add(StatCache(user_id=user_id, key=key, value=value))
    else:
        row.value = value
        row.computed_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return value


def _games(session: Session, user_id: int, days: Optional[int] = None,
           time_class: Optional[str] = None) -> list[Game]:
    q = select(Game).where(Game.user_id == user_id)
    if days:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        q = q.where(Game.end_time >= since)
    if time_class:
        q = q.where(Game.time_class == time_class)
    return list(session.scalars(q.order_by(Game.end_time)))


def _player_rating(g: Game) -> Optional[int]:
    if g.player_color == "white":
        return g.white_rating
    if g.player_color == "black":
        return g.black_rating
    return None


def _band(rating: Optional[int]) -> str:
    if rating is None:
        return "unknown"
    lo = (rating // 200) * 200
    return f"{lo}-{lo + 199}"


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard(session: Session, user_id: int, days: Optional[int] = None) -> dict:
    return _cached(session, user_id, f"dashboard:{days or 'all'}", lambda: _dashboard(session, user_id, days))


def _dashboard(session: Session, user_id: int, days: Optional[int]) -> dict:
    games = _games(session, user_id, days)
    rated = [g for g in games if g.player_result]

    by_tc: dict[str, list[Game]] = defaultdict(list)
    for g in games:
        by_tc[g.time_class or "unknown"].append(g)

    ratings: dict[str, dict] = {}
    for tc, gs in by_tc.items():
        pts = [(g.end_time, _player_rating(g)) for g in gs if _player_rating(g) is not None]
        pts = [(t, r) for t, r in pts if t is not None]
        pts.sort(key=lambda x: x[0])
        if pts:
            vals = [r for _, r in pts]
            ratings[tc] = {
                "current": vals[-1],
                "peak": max(vals),
                "lowest": min(vals),
                "change": vals[-1] - vals[0] if len(vals) > 1 else 0,
                "count": len(vals),
                "history": [{"t": t.isoformat(), "rating": r} for t, r in pts],
            }

    # Results
    wins = sum(1 for g in rated if g.player_result == "win")
    losses = sum(1 for g in rated if g.player_result == "loss")
    draws = sum(1 for g in rated if g.player_result == "draw")
    total = wins + losses + draws
    win_rate = round(100.0 * wins / total, 1) if total else 0.0

    # Activity
    per_day = Counter(g.end_time.date().isoformat() for g in games if g.end_time)
    per_hour = Counter(f"{g.end_time.hour:02d}" for g in games if g.end_time)
    per_dow = Counter(g.end_time.strftime("%a") for g in games if g.end_time)
    session_lengths = Counter(g.end_time.date().isoformat() for g in games if g.end_time)
    avg_session = round(sum(session_lengths.values()) / len(session_lengths), 1) if session_lengths else 0

    by_color = {}
    for color in ("white", "black"):
        gs = [g for g in rated if g.player_color == color]
        w = sum(1 for g in gs if g.player_result == "win")
        by_color[color] = {
            "games": len(gs), "wins": w,
            "win_rate": round(100.0 * w / len(gs), 1) if gs else 0.0,
        }

    by_band = defaultdict(lambda: {"games": 0, "wins": 0})
    for g in rated:
        b = _band(g.opponent_rating)
        by_band[b]["games"] += 1
        by_band[b]["wins"] += int(g.player_result == "win")
    opponent_bands = {
        b: {**v, "win_rate": round(100.0 * v["wins"] / v["games"], 1)}
        for b, v in sorted(by_band.items())
    }

    # Streaks (most recent first)
    recent = sorted(rated, key=lambda g: g.end_time or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
    streak_type, streak_len = None, 0
    for g in recent:
        if streak_type is None:
            streak_type, streak_len = g.player_result, 1
        elif g.player_result == streak_type:
            streak_len += 1
        else:
            break

    # Analysis status
    status_counts = Counter(g.analysis_status for g in games)
    jobs = session.scalars(select(AnalysisJob).join(Game).where(Game.user_id == user_id)).all()
    job_counts = Counter(j.status for j in jobs)

    # Performance summary from analyzed games
    analyzed = [g for g in games if g.analysis_status == "done" and g.acpl is not None]
    perf = _performance_summary(analyzed)

    return {
        "totals": {
            "games": len(games), "wins": wins, "losses": losses, "draws": draws,
            "win_rate": win_rate,
            "rated_games": total,
        },
        "ratings": ratings,
        "activity": {
            "per_day": dict(per_day),
            "per_hour": dict(per_hour),
            "per_dow": dict(per_dow),
            "avg_session_games": avg_session,
            "by_time_class": {tc: len(gs) for tc, gs in by_tc.items()},
        },
        "by_color": by_color,
        "opponent_bands": opponent_bands,
        "streak": {"type": streak_type, "length": streak_len},
        "analysis": {
            "imported": len(games),
            "queued": status_counts.get("queued", 0),
            "analyzing": status_counts.get("analyzing", 0),
            "done": status_counts.get("done", 0),
            "failed": status_counts.get("failed", 0),
            "jobs": dict(job_counts),
        },
        "performance": perf,
        "recent_games": [_game_brief(g) for g in recent[:15]],
    }


def _performance_summary(games: list[Game]) -> dict:
    if not games:
        return {"analyzed_games": 0}
    acpls = [g.acpl for g in games if g.acpl is not None]
    accs = [g.accuracy for g in games if g.accuracy is not None]
    bpg = [g.blunders for g in games]
    mpg = [g.mistakes for g in games]
    ipg = [g.inaccuracies for g in games]
    return {
        "analyzed_games": len(games),
        "avg_acpl": round(sum(acpls) / len(acpls), 1) if acpls else None,
        "avg_accuracy": round(sum(accs) / len(accs), 1) if accs else None,
        "blunders_per_game": round(sum(bpg) / len(games), 2),
        "mistakes_per_game": round(sum(mpg) / len(games), 2),
        "inaccuracies_per_game": round(sum(ipg) / len(games), 2),
        "missed_wins": sum(g.missed_wins for g in games),
        "missed_mates": sum(g.missed_mates for g in games),
        "time_pressure_errors": sum(g.time_pressure_errors for g in games),
    }


def _game_brief(g: Game) -> dict:
    return {
        "id": g.id,
        "end_time": g.end_time.isoformat() if g.end_time else None,
        "opponent": g.opponent_username,
        "opponent_rating": g.opponent_rating,
        "player_rating": _player_rating(g),
        "color": g.player_color,
        "result": g.player_result,
        "time_class": g.time_class,
        "opening": g.opening_name,
        "eco": g.eco,
        "status": g.analysis_status,
        "blunders": g.blunders,
        "mistakes": g.mistakes,
        "acpl": g.acpl,
        "accuracy": g.accuracy,
    }


# ---------------------------------------------------------------------------
# Phase / breakdown statistics (move-level)
# ---------------------------------------------------------------------------

def phase_of_fen(fen: str) -> str:
    try:
        board = chess.Board(fen)
    except Exception:
        return "unknown"
    non_pawn = 0
    for pt, val in ((chess.KNIGHT, 1), (chess.BISHOP, 1), (chess.ROOK, 2), (chess.QUEEN, 4)):
        non_pawn += len(board.pieces(pt, chess.WHITE)) * val
        non_pawn += len(board.pieces(pt, chess.BLACK)) * val
    if board.fullmove_number <= 10:
        return "opening"
    if non_pawn <= 6:
        return "endgame"
    return "middlegame"


def move_breakdown(session: Session, user_id: int, days: Optional[int] = None) -> dict:
    return _cached(session, user_id, f"breakdown:{days or 'all'}",
                   lambda: _move_breakdown(session, user_id, days))


def _move_breakdown(session: Session, user_id: int, days: Optional[int]) -> dict:
    games = _games(session, user_id, days)
    game_ids = [g.id for g in games]
    if not game_ids:
        return {"by_phase": {}, "by_color": {}, "by_time_class": {}, "by_opponent_band": {}}

    moves = session.scalars(select(GameMove).where(GameMove.game_id.in_(game_ids))).all()
    gmap = {g.id: g for g in games}

    by_phase: dict[str, dict] = defaultdict(lambda: {"moves": 0, "loss_sum": 0, "blunders": 0, "mistakes": 0})
    by_color = defaultdict(lambda: {"moves": 0, "loss_sum": 0, "blunders": 0, "mistakes": 0})
    by_tc = defaultdict(lambda: {"moves": 0, "loss_sum": 0, "blunders": 0})
    by_band = defaultdict(lambda: {"moves": 0, "loss_sum": 0, "blunders": 0})

    for mv in moves:
        g = gmap.get(mv.game_id)
        if g is None or g.player_color is None or mv.color != g.player_color:
            continue
        if mv.classification in ("forced", "book") or mv.cp_loss is None:
            continue
        phase = phase_of_fen(mv.fen_before)
        for bucket in (by_phase[phase], by_color[mv.color],
                       by_tc[g.time_class or "unknown"], by_band[_band(g.opponent_rating)]):
            bucket["moves"] += 1
            bucket["loss_sum"] += mv.cp_loss
            if mv.classification == "blunder":
                bucket["blunders"] += 1
            if bucket.get("mistakes") is not None and mv.classification == "mistake":
                bucket["mistakes"] += 1

    def finalize(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            moves_n = v["moves"] or 1
            out[k] = {
                **v,
                "acpl": round(v["loss_sum"] / moves_n, 1),
                "blunders_per_100": round(100.0 * v["blunders"] / moves_n, 2),
            }
        return out

    return {
        "by_phase": finalize(by_phase),
        "by_color": finalize(by_color),
        "by_time_class": finalize(by_tc),
        "by_opponent_band": finalize(by_band),
    }


# ---------------------------------------------------------------------------
# Progress / long-term
# ---------------------------------------------------------------------------

def progress(session: Session, user_id: int, window: int = 50) -> dict:
    return _cached(session, user_id, f"progress:{window}", lambda: _progress(session, user_id, window))


def _progress(session: Session, user_id: int, window: int) -> dict:
    analyzed = [g for g in _games(session, user_id) if g.analysis_status == "done" and g.end_time]
    analyzed.sort(key=lambda g: g.end_time)
    if not analyzed:
        return {"has_data": False}

    recent = analyzed[-window:]
    prev = analyzed[-2 * window:-window]

    def agg(gs: list[Game]) -> dict:
        if not gs:
            return {}
        acpls = [g.acpl for g in gs if g.acpl is not None]
        return {
            "games": len(gs),
            "avg_acpl": round(sum(acpls) / len(acpls), 1) if acpls else None,
            "blunders_pg": round(sum(g.blunders for g in gs) / len(gs), 2),
            "win_rate": round(100.0 * sum(1 for g in gs if g.player_result == "win")
                              / max(1, sum(1 for g in gs if g.player_result)), 1),
        }

    return {
        "has_data": True,
        "window": window,
        "recent": agg(recent),
        "previous": agg(prev),
        "series": [
            {"t": g.end_time.isoformat(), "acpl": g.acpl, "accuracy": g.accuracy,
             "blunders": g.blunders, "rating": _player_rating(g)}
            for g in analyzed
        ],
        "disclaimer": "Association only: improvements in metrics and rating changes are reported together, not as proven causation.",
    }
