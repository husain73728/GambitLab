"""Game library, game detail, analysis control and PGN export."""
from __future__ import annotations

import datetime as dt
import io
from typing import Optional

import chess
import chess.pgn
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..analysis.stats import _player_rating
from ..db import get_session
from ..deps import get_current_user
from ..jobs import enqueue_game, worker
from ..models import AnalysisJob, Annotation, Game, GameMove, TacticalEvent

router = APIRouter(prefix="/api", tags=["games"])

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


class FavoriteReq(BaseModel):
    value: bool


class NotesReq(BaseModel):
    notes: str


class AnnotationReq(BaseModel):
    ply: Optional[int] = None
    comment: Optional[str] = None
    tags: Optional[list[str]] = None
    kind: str = "note"


def _brief(g: Game) -> dict:
    return {
        "id": g.id,
        "end_time": g.end_time.isoformat() if g.end_time else None,
        "opponent": g.opponent_username,
        "opponent_rating": g.opponent_rating,
        "player_rating": _player_rating(g),
        "color": g.player_color,
        "result": g.player_result,
        "time_class": g.time_class,
        "time_control": g.time_control,
        "opening": g.opening_name,
        "eco": g.eco,
        "termination": g.termination,
        "moves": g.move_count,
        "status": g.analysis_status,
        "progress": g.analysis_progress,
        "acpl": g.acpl,
        "accuracy": g.accuracy,
        "blunders": g.blunders,
        "mistakes": g.mistakes,
        "inaccuracies": g.inaccuracies,
        "missed_wins": g.missed_wins,
        "tactical_events": g.tactical_events_count,
        "favorite": g.is_favorite,
    }


@router.get("/games")
def list_games(
    session: Session = Depends(get_session),
    days: Optional[int] = None,
    time_class: Optional[str] = None,
    color: Optional[str] = None,
    result: Optional[str] = None,
    opponent: Optional[str] = None,
    min_opp_rating: Optional[int] = None,
    max_opp_rating: Optional[int] = None,
    opening: Optional[str] = None,
    status: Optional[str] = None,
    min_blunders: Optional[int] = None,
    termination: Optional[str] = None,
    has_missed_win: Optional[bool] = None,
    has_time_pressure_error: Optional[bool] = None,
    favorite: Optional[bool] = None,
    sort: str = "date_desc",
    limit: int = 50,
    offset: int = 0,
):
    user = get_current_user(session)
    q = select(Game).where(Game.user_id == user.id)
    if days:
        q = q.where(Game.end_time >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days))
    if time_class:
        q = q.where(Game.time_class == time_class)
    if color:
        q = q.where(Game.player_color == color)
    if result:
        q = q.where(Game.player_result == result)
    if opponent:
        q = q.where(Game.opponent_username.ilike(f"%{opponent}%"))
    if min_opp_rating is not None:
        q = q.where(Game.opponent_rating >= min_opp_rating)
    if max_opp_rating is not None:
        q = q.where(Game.opponent_rating <= max_opp_rating)
    if opening:
        q = q.where(or_(Game.opening_name.ilike(f"%{opening}%"), Game.eco.ilike(f"%{opening}%")))
    if status:
        q = q.where(Game.analysis_status == status)
    if min_blunders is not None:
        q = q.where(Game.blunders >= min_blunders)
    if termination:
        q = q.where(Game.termination.ilike(f"%{termination}%"))
    if has_missed_win:
        q = q.where(Game.missed_wins > 0)
    if has_time_pressure_error:
        q = q.where(Game.time_pressure_errors > 0)
    if favorite:
        q = q.where(Game.is_favorite == True)  # noqa: E712

    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0
    order = {
        "date_desc": Game.end_time.desc(),
        "date_asc": Game.end_time.asc(),
        "blunders": Game.blunders.desc(),
        "acpl": Game.acpl.desc(),
    }.get(sort, Game.end_time.desc())
    rows = session.scalars(q.order_by(order).limit(min(limit, 200)).offset(offset)).all()
    return {"total": total, "games": [_brief(g) for g in rows]}


@router.get("/games/{game_id}")
def game_detail(game_id: int, session: Session = Depends(get_session)):
    get_current_user(session)
    g = session.get(Game, game_id)
    if g is None:
        raise HTTPException(status_code=404, detail="game not found")
    moves = session.scalars(
        select(GameMove).where(GameMove.game_id == game_id).order_by(GameMove.ply)
    ).all()
    anns = session.scalars(select(Annotation).where(Annotation.game_id == game_id)).all()
    tactics = session.scalars(select(TacticalEvent).where(TacticalEvent.game_id == game_id)).all()
    return {
        "game": {
            **_brief(g),
            "white": g.white_username, "black": g.black_username,
            "white_rating": g.white_rating, "black_rating": g.black_rating,
            "white_result": g.white_result, "black_result": g.black_result,
            "start_time": g.start_time.isoformat() if g.start_time else None,
            "notes": g.notes, "source": g.source, "rated": g.rated,
            "has_clock": g.has_clock_data, "error": g.analysis_error,
            "best_move_rate": g.best_move_rate, "missed_mates": g.missed_mates,
        },
        "moves": [_move_dict(m) for m in moves],
        "annotations": [{"ply": a.ply, "comment": a.comment, "tags": a.tags, "kind": a.kind} for a in anns],
        "tactics": [{"ply": t.ply, "motif": t.motif, "kind": t.kind, "loss": t.eval_loss_cp,
                     "confidence": t.confidence, "detail": t.detail} for t in tactics],
    }


def _move_dict(m: GameMove) -> dict:
    return {
        "ply": m.ply, "move_number": m.move_number, "color": m.color, "san": m.san, "uci": m.uci,
        "fen_before": m.fen_before, "fen_after": m.fen_after,
        "is_capture": m.is_capture, "captured_piece": m.captured_piece,
        "is_check": m.is_check, "is_mate": m.is_mate,
        "clock": m.clock_seconds, "think": m.think_seconds,
        "eval_cp": m.eval_cp, "eval_mate_in": m.eval_mate_in,
        "best_uci": m.best_uci, "best_eval_cp": m.best_eval_cp, "best_mate_in": m.best_mate_in,
        "cp_loss": m.cp_loss, "classification": m.classification,
        "provisional": m.provisional, "alternatives": m.alternatives, "explanation": m.explanation,
        "material": _material_balance(m.fen_before),
    }


def _material_balance(fen: str) -> dict:
    try:
        b = chess.Board(fen)
    except Exception:
        return {"white": 0, "black": 0}
    w = sum(len(b.pieces(pt, chess.WHITE)) * v for pt, v in PIECE_VALUES.items())
    bl = sum(len(b.pieces(pt, chess.BLACK)) * v for pt, v in PIECE_VALUES.items())
    return {"white": w, "black": bl, "diff": w - bl}


@router.post("/games/{game_id}/analyze")
def analyze_game(game_id: int, session: Session = Depends(get_session)):
    user = get_current_user(session)
    g = session.get(Game, game_id)
    if g is None or g.user_id != user.id:
        raise HTTPException(status_code=404, detail="game not found")
    job = enqueue_game(session, game_id, priority=10)
    return {"job_id": job.id, "status": job.status}


@router.post("/games/{game_id}/favorite")
def set_favorite(game_id: int, req: FavoriteReq, session: Session = Depends(get_session)):
    get_current_user(session)
    g = session.get(Game, game_id)
    if g is None:
        raise HTTPException(status_code=404, detail="game not found")
    g.is_favorite = req.value
    session.commit()
    return {"favorite": g.is_favorite}


@router.post("/games/{game_id}/notes")
def set_notes(game_id: int, req: NotesReq, session: Session = Depends(get_session)):
    get_current_user(session)
    g = session.get(Game, game_id)
    if g is None:
        raise HTTPException(status_code=404, detail="game not found")
    g.notes = req.notes
    session.commit()
    return {"ok": True}


@router.post("/games/{game_id}/annotations")
def add_annotation(game_id: int, req: AnnotationReq, session: Session = Depends(get_session)):
    get_current_user(session)
    g = session.get(Game, game_id)
    if g is None:
        raise HTTPException(status_code=404, detail="game not found")
    ann = Annotation(game_id=game_id, ply=req.ply, comment=req.comment,
                     tags=req.tags or [], kind=req.kind)
    session.add(ann)
    session.commit()
    return {"id": ann.id}


@router.get("/games/{game_id}/pgn")
def export_pgn(game_id: int, annotated: bool = True, session: Session = Depends(get_session)):
    get_current_user(session)
    g = session.get(Game, game_id)
    if g is None:
        raise HTTPException(status_code=404, detail="game not found")
    if not annotated:
        return {"pgn": g.raw_pgn}

    game = chess.pgn.read_game(io.StringIO(g.raw_pgn))
    if game is None:
        return {"pgn": g.raw_pgn}
    moves = {m.ply: m for m in session.scalars(
        select(GameMove).where(GameMove.game_id == game_id))}
    node = game
    ply = 0
    while node.variations:
        node = node.variation(0)
        ply += 1
        mv = moves.get(ply)
        if mv and mv.classification:
            tag = {"blunder": "??", "mistake": "?", "inaccuracy": "?!"}.get(mv.classification, "")
            note = f"[{mv.classification}{(' ' + tag) if tag else ''}]"
            if mv.cp_loss is not None:
                note += f" loss {mv.cp_loss}cp"
            if mv.explanation:
                note += f". {mv.explanation}"
            node.comment = (node.comment + " " + note).strip()
    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
    return {"pgn": game.accept(exporter)}


@router.get("/analysis/status")
def analysis_status(session: Session = Depends(get_session)):
    user = get_current_user(session)
    statuses = dict(session.execute(
        select(Game.analysis_status, func.count()).where(Game.user_id == user.id)
        .group_by(Game.analysis_status)
    ).all())
    jobs = session.scalars(
        select(AnalysisJob).join(Game).where(Game.user_id == user.id).order_by(AnalysisJob.id.desc()).limit(20)
    ).all()
    return {
        "games": statuses,
        "running": len(worker.running),
        "jobs": [
            {"id": j.id, "game_id": j.game_id, "status": j.status, "stage": j.stage,
             "progress": j.progress, "error": j.error, "attempts": j.attempts}
            for j in jobs
        ],
    }


@router.post("/analysis/{job_id}/cancel")
def cancel_job(job_id: int, session: Session = Depends(get_session)):
    get_current_user(session)
    job = session.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status == "queued":
        job.status = "cancelled"
        session.commit()
    return {"status": job.status}
