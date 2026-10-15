"""Personalized training: weakness detection, priorities, puzzles, plans.

All priorities come from deterministic formulas over stored analysis; every
recommendation records the evidence that produced it.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Optional

import chess
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    Game,
    GameMove,
    Recommendation,
    TacticalEvent,
    TrainingAttempt,
    TrainingExercise,
    TrainingPlan,
)

# ---------------------------------------------------------------------------
# Weakness detection
# ---------------------------------------------------------------------------

# Transparent priority weights (sum = 1.0).
W_FREQUENCY = 0.40
W_LOSS = 0.30
W_GAMES = 0.15
W_RECENCY = 0.10
W_CONFIDENCE = 0.05


def _norm(value: float, scale: float) -> float:
    return max(0.0, min(1.0, value / scale)) if scale else 0.0


def weakness_report(session: Session, user_id: int, days: Optional[int] = None) -> list[dict]:
    since = None
    if days:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)

    gq = select(Game).where(Game.user_id == user_id, Game.analysis_status == "done")
    if since is not None:
        gq = gq.where(Game.end_time >= since)
    games = list(session.scalars(gq))
    if not games:
        return []
    game_ids = [g.id for g in games]
    total_games = len(games)

    events = session.scalars(
        select(TacticalEvent).where(TacticalEvent.game_id.in_(game_ids))
    ).all()
    moves = session.scalars(
        select(GameMove).where(GameMove.game_id.in_(game_ids)).order_by(GameMove.ply)
    ).all()
    gmap = {g.id: g for g in games}

    weaknesses: list[dict] = []

    # 1) Tactical motifs (missed vs found).
    by_motif: dict[str, dict] = defaultdict(lambda: {"missed": 0, "found": 0, "loss": 0, "games": set(), "recent": 0})
    for ev in events:
        m = by_motif[ev.motif]
        m[ev.kind] += 1
        m["loss"] += ev.eval_loss_cp
        m["games"].add(ev.game_id)
        g = gmap.get(ev.game_id)
        if g and g.end_time and g.end_time >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30):
            m["recent"] += 1

    for motif, m in by_motif.items():
        if m["missed"] == 0:
            continue
        avg_loss = m["loss"] / max(1, m["missed"] + m["found"])
        priority = (
            W_FREQUENCY * _norm(m["missed"], 20)
            + W_LOSS * _norm(avg_loss, 400)
            + W_GAMES * _norm(len(m["games"]), max(1, total_games))
            + W_RECENCY * _norm(m["recent"], 10)
            + W_CONFIDENCE * 0.8
        )
        weaknesses.append({
            "category": "tactics",
            "motif": motif,
            "label": f"Missed {motif.replace('_', ' ')}s",
            "missed": m["missed"], "found": m["found"],
            "games_affected": len(m["games"]),
            "avg_loss": round(avg_loss, 1),
            "recent": m["recent"],
            "priority": round(priority, 3),
            "evidence": {"motif": motif, "missed": m["missed"], "found": m["found"]},
        })

    # 2) Blunder prevention / phase weaknesses from move classifications.
    phase_stats: dict[str, dict] = defaultdict(lambda: {"loss": 0, "n": 0, "blunders": 0, "games": set()})
    for mv in moves:
        g = gmap.get(mv.game_id)
        if g is None or g.player_color is None or mv.color != g.player_color:
            continue
        if mv.classification in ("forced", "book") or mv.cp_loss is None:
            continue
        ph = _phase(mv.fen_before)
        phase_stats[ph]["loss"] += mv.cp_loss
        phase_stats[ph]["n"] += 1
        phase_stats[ph]["games"].add(mv.game_id)
        if mv.classification == "blunder":
            phase_stats[ph]["blunders"] += 1

    for ph, s in phase_stats.items():
        if s["n"] == 0:
            continue
        acpl = s["loss"] / s["n"]
        bpg = s["blunders"] / max(1, len(s["games"]))
        priority = (
            W_FREQUENCY * _norm(bpg, 3)
            + W_LOSS * _norm(acpl, 180)
            + W_GAMES * _norm(len(s["games"]), total_games)
            + W_CONFIDENCE * 0.7
        )
        weaknesses.append({
            "category": "phase",
            "phase": ph,
            "label": f"{ph.capitalize()} play",
            "acpl": round(acpl, 1),
            "blunders_per_game": round(bpg, 2),
            "games_affected": len(s["games"]),
            "priority": round(priority, 3),
            "evidence": {"phase": ph, "acpl": round(acpl, 1), "moves": s["n"]},
        })

    # 3) Time management.
    tp = [(mv, gmap.get(mv.game_id)) for mv in moves]
    tp_errs = 0
    tp_games = set()
    for mv, g in tp:
        if g is None or g.player_color is None or mv.color != g.player_color:
            continue
        if mv.classification in ("blunder", "mistake") and mv.clock_seconds is not None and mv.clock_seconds <= 15:
            tp_errs += 1
            tp_games.add(mv.game_id)
    if tp_errs:
        priority = (W_FREQUENCY * _norm(tp_errs, 15) + W_GAMES * _norm(len(tp_games), total_games)
                    + W_CONFIDENCE * 0.5)
        weaknesses.append({
            "category": "time_management",
            "label": "Errors under time pressure",
            "errors": tp_errs,
            "games_affected": len(tp_games),
            "priority": round(priority, 3),
            "evidence": {"errors": tp_errs, "threshold_seconds": 15},
        })

    # 4) Conversion (missed wins).
    missed_wins = sum(g.missed_wins for g in games)
    if missed_wins:
        priority = W_FREQUENCY * _norm(missed_wins, 10) + W_CONFIDENCE * 0.7
        weaknesses.append({
            "category": "conversion",
            "label": "Converting winning positions",
            "missed_wins": missed_wins,
            "games_affected": sum(1 for g in games if g.missed_wins),
            "priority": round(priority, 3),
            "evidence": {"missed_wins": missed_wins},
        })

    weaknesses.sort(key=lambda w: w["priority"], reverse=True)
    return weaknesses


def _phase(fen: str) -> str:
    try:
        board = chess.Board(fen)
    except Exception:
        return "unknown"
    if board.fullmove_number <= 10:
        return "opening"
    non_pawn = sum(
        len(board.pieces(pt, c)) * v
        for pt, v in ((chess.KNIGHT, 1), (chess.BISHOP, 1), (chess.ROOK, 2), (chess.QUEEN, 4))
        for c in (chess.WHITE, chess.BLACK)
    )
    return "endgame" if non_pawn <= 6 else "middlegame"


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def generate_recommendations(session: Session, user_id: int) -> list[Recommendation]:
    report = weakness_report(session, user_id)
    session.execute(
        delete(Recommendation).where(Recommendation.user_id == user_id, Recommendation.status == "open")
    )
    out: list[Recommendation] = []
    for w in report[:6]:
        rec = Recommendation(
            user_id=user_id,
            category=w["category"],
            title=_rec_title(w),
            reason=_rec_reason(w),
            priority=w["priority"],
            evidence=w,
        )
        session.add(rec)
        out.append(rec)
    session.commit()
    return out


def _rec_title(w: dict) -> str:
    cat = w["category"]
    if cat == "tactics":
        return f"Train {w.get('motif', 'tactics').replace('_', ' ')} recognition"
    if cat == "phase":
        return f"Improve your {w.get('phase', '')} play".strip()
    if cat == "time_management":
        return "Practise time management"
    if cat == "conversion":
        return "Convert winning positions"
    return w.get("label", "Improve")


def _rec_reason(w: dict) -> str:
    if w["category"] == "tactics":
        return (f"You missed {w['missed']} {w['motif'].replace('_', ' ')} opportunity(ies) across "
                f"{w['games_affected']} game(s), costing on average {w['avg_loss']}cp.")
    if w["category"] == "phase":
        return (f"Your average centipawn loss in the {w['phase']} is {w['acpl']}cp over "
                f"{w['games_affected']} game(s), with {w['blunders_per_game']} blunders/game.")
    if w["category"] == "time_management":
        return f"{w['errors']} serious error(s) occurred with 15 seconds or less on the clock."
    if w["category"] == "conversion":
        return f"You missed a win in {w['games_affected']} game(s) from a clearly winning position."
    return w["label"]


# ---------------------------------------------------------------------------
# Weekly plan
# ---------------------------------------------------------------------------

def build_plan(session: Session, user_id: int, minutes: int = 120) -> TrainingPlan:
    recs = generate_recommendations(session, user_id)
    items = []
    if recs:
        total = sum(r.priority for r in recs) or 1.0
        for r in recs:
            alloc = max(10, int(minutes * r.priority / total))
            items.append({
                "category": r.category,
                "title": r.title,
                "reason": r.reason,
                "minutes": alloc,
                "priority": r.priority,
            })
    week_start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=dt.datetime.now().weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    plan = TrainingPlan(
        user_id=user_id, week_start=week_start, minutes_budget=minutes, items=items,
        summary=("Focus on: " + ", ".join(i["title"] for i in items[:3])) if items else "Not enough analysed games yet.",
    )
    session.add(plan)
    session.commit()
    return plan


# ---------------------------------------------------------------------------
# Puzzles
# ---------------------------------------------------------------------------

def generate_puzzles(session: Session, user_id: int, limit: int = 40) -> int:
    """Create exercises from the player's own mistakes/opportunities."""
    games = list(session.scalars(
        select(Game).where(Game.user_id == user_id, Game.analysis_status == "done")
    ))
    if not games:
        return 0
    existing = set(session.scalars(
        select(TrainingExercise.fen).where(TrainingExercise.user_id == user_id)
    ))
    created = 0
    for g in games:
        if created >= limit:
            break
        moves = session.scalars(
            select(GameMove).where(GameMove.game_id == g.id, GameMove.color == g.player_color)
            .order_by(GameMove.ply)
        ).all()
        for mv in moves:
            if created >= limit:
                break
            if mv.classification not in ("blunder", "mistake", "missed_win", "missed_mate"):
                continue
            if not mv.best_uci or mv.fen_before in existing:
                continue
            if not _verify_solution(mv.fen_before, mv.best_uci):
                continue
            accepted = [mv.best_uci]
            for alt in (mv.alternatives or [])[1:3]:
                u = alt.get("uci")
                if u and u != mv.best_uci:
                    accepted.append(u)
            motif = session.scalar(
                select(TacticalEvent.motif).where(
                    TacticalEvent.game_id == g.id, TacticalEvent.ply == mv.ply
                ).limit(1)
            )
            category = "tactics" if motif else "calculation"
            difficulty = _difficulty(mv)
            session.add(TrainingExercise(
                user_id=user_id, fen=mv.fen_before, side_to_move=mv.color,
                category=category, motif=motif,
                solution_uci=mv.best_uci, accepted=accepted,
                objective=(mv.explanation or "Find the best move."),
                difficulty=difficulty, source_game_id=g.id, source_ply=mv.ply,
                due_at=dt.datetime.now(dt.timezone.utc),
            ))
            existing.add(mv.fen_before)
            created += 1
    session.commit()
    return created


def _verify_solution(fen: str, uci: str) -> bool:
    try:
        board = chess.Board(fen)
        move = chess.Move.from_uci(uci)
        return move in board.legal_moves
    except Exception:
        return False


def _difficulty(mv: GameMove) -> int:
    if mv.classification == "missed_mate":
        return 4
    if (mv.cp_loss or 0) >= 400:
        return 4
    if (mv.cp_loss or 0) >= 200:
        return 3
    return 2


def record_attempt(session: Session, exercise_id: int, move_uci: str,
                   time_ms: Optional[int] = None, hint: bool = False) -> dict:
    ex = session.get(TrainingExercise, exercise_id)
    if ex is None:
        raise ValueError("exercise not found")
    uci = (move_uci or "").strip().lower()
    correct = uci in {a.lower() for a in ([ex.solution_uci] + list(ex.accepted or []))}
    ex.attempts += 1
    ex.solves += int(correct)
    if correct:
        # spaced repetition: push next review out
        ex.due_at = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=min(30, 2 ** min(ex.solves, 5)))
    session.add(TrainingAttempt(exercise_id=exercise_id, user_move_uci=uci, correct=correct,
                                time_ms=time_ms, hint_used=hint))
    session.commit()
    return {
        "correct": correct,
        "solution": ex.solution_uci,
        "accepted": ex.accepted,
        "objective": ex.objective,
        "attempts": ex.attempts,
        "solves": ex.solves,
    }


def training_stats(session: Session, user_id: int) -> dict:
    exs = list(session.scalars(select(TrainingExercise).where(TrainingExercise.user_id == user_id)))
    attempts = session.scalar(
        select(func.count(TrainingAttempt.id)).join(TrainingExercise).where(TrainingExercise.user_id == user_id)
    ) or 0
    solved = sum(1 for e in exs if e.solves > 0)
    return {
        "exercises": len(exs),
        "attempts": attempts,
        "solved": solved,
        "solve_rate": round(100.0 * solved / len(exs), 1) if exs else 0.0,
        "by_category": _count_by(exs, "category"),
        "by_motif": _count_by(exs, "motif"),
        "due": sum(1 for e in exs if e.due_at and e.due_at <= dt.datetime.now(dt.timezone.utc)),
    }


def _count_by(items, attr: str) -> dict:
    out: dict[str, int] = defaultdict(int)
    for it in items:
        key = getattr(it, attr) or "unknown"
        out[key] += 1
    return dict(out)
