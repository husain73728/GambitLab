"""Openings, tactics, clock, training, repertoire and assistant routes."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..analysis.assistant import answer as assistant_answer
from ..analysis.clock import clock_report
from ..analysis.openings import compare_to_repertoire, opening_report, repertoire_report
from ..analysis.stats import move_breakdown
from ..analysis.training import (
    build_plan,
    generate_puzzles,
    generate_recommendations,
    record_attempt,
    training_stats,
    weakness_report,
)
from ..db import get_session
from ..deps import get_current_user
from ..models import Game, RepertoireLine, TacticalEvent, TrainingExercise, TrainingPlan

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/openings")
def openings(days: Optional[int] = None, color: Optional[str] = None,
             session: Session = Depends(get_session)):
    user = get_current_user(session)
    return opening_report(session, user.id, days, color)


@router.get("/openings/compare/{game_id}")
def openings_compare(game_id: int, session: Session = Depends(get_session)):
    user = get_current_user(session)
    return compare_to_repertoire(session, user.id, game_id)


@router.get("/breakdown")
def breakdown(days: Optional[int] = None, session: Session = Depends(get_session)):
    user = get_current_user(session)
    return move_breakdown(session, user.id, days)


@router.get("/tactics")
def tactics(days: Optional[int] = None, session: Session = Depends(get_session)):
    user = get_current_user(session)
    return {
        "weaknesses": [w for w in weakness_report(session, user.id, days) if w["category"] == "tactics"],
        "motifs": _tactic_aggregate(session, user.id),
    }


def _tactic_aggregate(session: Session, user_id: int) -> list[dict]:
    events = session.scalars(
        select(TacticalEvent).where(TacticalEvent.user_id == user_id).order_by(TacticalEvent.id.desc())
    ).all()
    agg: dict[str, dict] = defaultdict(lambda: {
        "motif": "", "found": 0, "missed": 0, "loss_sum": 0, "games": set(),
        "examples": [], "recent30": 0, "historical": 0,
    })
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    for ev in events:
        a = agg[ev.motif]
        a["motif"] = ev.motif
        a[ev.kind] += 1
        a["loss_sum"] += ev.eval_loss_cp
        a["games"].add(ev.game_id)
        if ev.created_at and ev.created_at >= cutoff:
            a["recent30"] += 1
        else:
            a["historical"] += 1
        if len(a["examples"]) < 5 and ev.fen:
            a["examples"].append({"game_id": ev.game_id, "ply": ev.ply, "fen": ev.fen,
                                  "kind": ev.kind, "loss": ev.eval_loss_cp})
    out = []
    for motif, a in agg.items():
        total = a["found"] + a["missed"]
        out.append({
            "motif": motif,
            "label": motif.replace("_", " "),
            "found": a["found"], "missed": a["missed"],
            "games_affected": len(a["games"]),
            "avg_loss": round(a["loss_sum"] / total, 1) if total else 0,
            "recent30": a["recent30"], "historical": a["historical"],
            "examples": a["examples"],
        })
    out.sort(key=lambda x: x["missed"], reverse=True)
    return out


@router.get("/clock")
def clock(days: Optional[int] = None, session: Session = Depends(get_session)):
    user = get_current_user(session)
    return clock_report(session, user.id, days)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

class PlanReq(BaseModel):
    minutes: int = 120


class PuzzleReq(BaseModel):
    limit: int = 30


class AttemptReq(BaseModel):
    exercise_id: int
    move_uci: str
    time_ms: Optional[int] = None
    hint: bool = False


@router.get("/training/weaknesses")
def training_weaknesses(days: Optional[int] = None, session: Session = Depends(get_session)):
    user = get_current_user(session)
    return {"weaknesses": weakness_report(session, user.id, days)}


@router.get("/training/plan")
def training_plan(session: Session = Depends(get_session)):
    user = get_current_user(session)
    plan = session.scalar(
        select(TrainingPlan).where(TrainingPlan.user_id == user.id).order_by(TrainingPlan.id.desc())
    )
    recs = generate_recommendations(session, user.id)
    return {
        "plan": ({"week_start": plan.week_start.isoformat(), "minutes": plan.minutes_budget,
                  "items": plan.items, "summary": plan.summary} if plan else None),
        "recommendations": [
            {"id": r.id, "category": r.category, "title": r.title, "reason": r.reason,
             "priority": r.priority, "evidence": r.evidence} for r in recs
        ],
    }


@router.post("/training/plan/generate")
def training_plan_generate(req: PlanReq, session: Session = Depends(get_session)):
    user = get_current_user(session)
    plan = build_plan(session, user.id, req.minutes)
    return {"week_start": plan.week_start.isoformat(), "minutes": plan.minutes_budget,
            "items": plan.items, "summary": plan.summary}


@router.post("/training/exercises/generate")
def training_generate(req: PuzzleReq, session: Session = Depends(get_session)):
    user = get_current_user(session)
    n = generate_puzzles(session, user.id, req.limit)
    return {"created": n}


@router.get("/training/exercises")
def training_exercises(category: Optional[str] = None, due_only: bool = False,
                       limit: int = 50, session: Session = Depends(get_session)):
    user = get_current_user(session)
    q = select(TrainingExercise).where(TrainingExercise.user_id == user.id)
    if category:
        q = q.where(TrainingExercise.category == category)
    if due_only:
        q = q.where(TrainingExercise.due_at <= dt.datetime.now(dt.timezone.utc))
    rows = session.scalars(q.order_by(TrainingExercise.due_at).limit(limit)).all()
    return {"exercises": [
        {"id": e.id, "fen": e.fen, "side_to_move": e.side_to_move, "category": e.category,
         "motif": e.motif, "difficulty": e.difficulty, "attempts": e.attempts, "solves": e.solves,
         "objective": e.objective, "source_game": e.source_game_id, "source_ply": e.source_ply}
        for e in rows
    ]}


@router.post("/training/attempt")
def training_attempt(req: AttemptReq, session: Session = Depends(get_session)):
    try:
        return record_attempt(session, req.exercise_id, req.move_uci, req.time_ms, req.hint)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/training/stats")
def training_stats_route(session: Session = Depends(get_session)):
    user = get_current_user(session)
    return training_stats(session, user.id)


# ---------------------------------------------------------------------------
# Repertoire
# ---------------------------------------------------------------------------

class RepertoireReq(BaseModel):
    name: str
    color: str
    moves_uci: list[str]
    checkpoints: Optional[list[int]] = None


@router.get("/repertoire")
def repertoire(session: Session = Depends(get_session)):
    user = get_current_user(session)
    return repertoire_report(session, user.id)


@router.post("/repertoire")
def repertoire_add(req: RepertoireReq, session: Session = Depends(get_session)):
    user = get_current_user(session)
    line = RepertoireLine(user_id=user.id, name=req.name, color=req.color,
                          moves_uci=req.moves_uci, checkpoints=req.checkpoints or [])
    session.add(line)
    session.commit()
    return {"id": line.id}


@router.delete("/repertoire/{line_id}")
def repertoire_delete(line_id: int, session: Session = Depends(get_session)):
    get_current_user(session)
    line = session.get(RepertoireLine, line_id)
    if line is None:
        raise HTTPException(status_code=404, detail="not found")
    session.delete(line)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Assistant
# ---------------------------------------------------------------------------

@router.get("/assistant")
def assistant(q: str, session: Session = Depends(get_session)):
    user = get_current_user(session)
    return assistant_answer(session, user.id, q)
