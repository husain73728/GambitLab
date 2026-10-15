"""Deterministic natural-language assistant.

Answers are computed from stored data with SQL/Python only. No language model
invents evaluations or statistics; every answer links to the games/moves behind it.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Game, GameMove
from .openings import opening_report
from .stats import _games, move_breakdown, progress
from .training import build_plan, weakness_report


def answer(session: Session, user_id: int, question: str) -> dict:
    q = (question or "").lower().strip()
    if not q:
        return _insufficient("Ask about your games, mistakes, openings, tactics, endgames or training.")

    if "lose" in q or "lost" in q or "why did i" in q:
        return _why_lose(session, user_id)
    if "mistake" in q or "blunder" in q:
        return _biggest_mistakes(session, user_id)
    if "opening" in q:
        return _openings(session, user_id)
    if "black" in q or "white" in q or "color" in q:
        return _by_color(session, user_id, q)
    if "tactic" in q or "pattern" in q:
        return _tactics(session, user_id)
    if "endgame" in q or "improve" in q:
        return _endgames(session, user_id)
    if "practice" in q or "train" in q or "this week" in q:
        return _practice(session, user_id)
    return _insufficient(
        "I can answer questions about losses, mistakes, openings, colours, tactics, "
        "endgames and what to practise, using your stored games and engine analysis."
    )


def _insufficient(msg: str) -> dict:
    return {"answer": msg, "evidence": [], "insufficient": True}


def _why_lose(session: Session, user_id: int) -> dict:
    games = [g for g in _games(session, user_id) if g.player_result == "loss" and g.end_time]
    if not games:
        return _insufficient("No losses stored yet.")
    g = sorted(games, key=lambda x: x.end_time, reverse=True)[0]
    moves = session.scalars(
        select(GameMove).where(GameMove.game_id == g.id, GameMove.color == g.player_color)
        .order_by(GameMove.cp_loss.desc())
    ).all()
    worst = [m for m in moves if m.classification in ("blunder", "mistake", "missed_win", "missed_mate")][:3]
    if not worst:
        return {
            "answer": f"Your most recent loss ({g.opponent_username}, {g.time_class}) has no stored major errors yet"
                      " — it may still be awaiting analysis.",
            "evidence": [{"game_id": g.id}],
            "insufficient": True,
        }
    lines = "; ".join(
        f"{m.move_number}{'.' if m.color == 'white' else '...'}{m.san} ({m.classification}, {m.cp_loss}cp lost"
        f"{', best was ' + m.best_uci if m.best_uci else ''})" for m in worst
    )
    return {
        "answer": f"In your last loss as {g.player_color} vs {g.opponent_username}, the decisive errors were: {lines}. "
                  f"Opening: {g.opening_name or 'unknown'}.",
        "evidence": [{"game_id": g.id, "ply": m.ply, "san": m.san, "classification": m.classification,
                      "cp_loss": m.cp_loss, "fen": m.fen_before} for m in worst],
        "insufficient": False,
    }


def _biggest_mistakes(session: Session, user_id: int) -> dict:
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    games = [g for g in _games(session, user_id) if g.end_time and g.end_time >= since]
    if not games:
        return _insufficient("No games analysed in the last 30 days.")
    ids = [g.id for g in games]
    moves = session.scalars(
        select(GameMove).where(GameMove.game_id.in_(ids))
        .where(GameMove.classification.in_(["blunder", "missed_win", "missed_mate"]))
        .order_by(GameMove.cp_loss.desc()).limit(3)
    ).all()
    if not moves:
        return {"answer": "No blunders or missed wins were found in the last 30 days of analysed games.",
                "evidence": [], "insufficient": False}
    ev = [{"game_id": m.game_id, "ply": m.ply, "san": m.san, "classification": m.classification,
           "cp_loss": m.cp_loss, "fen": m.fen_before, "best": m.best_uci} for m in moves]
    lines = "; ".join(f"{m.san} ({m.classification}, {m.cp_loss}cp, best {m.best_uci})" for m in moves)
    return {"answer": f"Your three biggest errors in the last 30 days: {lines}.",
            "evidence": ev, "insufficient": False}


def _openings(session: Session, user_id: int) -> dict:
    rep = opening_report(session, user_id)
    meaningful = [o for o in rep["openings"] if not o["sample_warning"]]
    if not meaningful:
        return _insufficient("Not enough games per opening yet (need at least 5 in an opening) to make a recommendation.")
    worst = sorted(meaningful, key=lambda o: o["score_rate"])[0]
    return {
        "answer": f"{worst['opening']} scores worst for you: {worst['score_rate']}% across "
                  f"{worst['games']} games. That is a place to prepare.",
        "evidence": [{"opening": worst["opening"], "games": worst["games"], "score_rate": worst["score_rate"]}],
        "insufficient": False,
    }


def _by_color(session: Session, user_id: int, q: str) -> dict:
    bd = move_breakdown(session, user_id).get("by_color", {})
    if not bd:
        return _insufficient("No analysed moves yet.")
    parts = []
    for color, s in bd.items():
        parts.append(f"as {color}: {s['acpl']} ACPL, {s['blunders_per_100']} blunders/100 moves")
    more = max(bd.items(), key=lambda kv: kv[1]["acpl"])
    return {
        "answer": "Your average centipawn loss by colour — " + "; ".join(parts) +
                  f". You lose more accuracy as {more[0]}.",
        "evidence": [{"color": c, **s} for c, s in bd.items()],
        "insufficient": False,
    }


def _tactics(session: Session, user_id: int) -> dict:
    report = [w for w in weakness_report(session, user_id) if w["category"] == "tactics"]
    if not report:
        return _insufficient("No recurring tactical weaknesses detected yet.")
    top = report[0]
    return {
        "answer": f"Your worst recurring tactical pattern is {top['motif'].replace('_', ' ')}: "
                  f"missed {top['missed']} time(s) across {top['games_affected']} game(s), "
                  f"average {top['avg_loss']}cp lost.",
        "evidence": [top],
        "insufficient": False,
    }


def _endgames(session: Session, user_id: int) -> dict:
    bd = move_breakdown(session, user_id).get("by_phase", {})
    if "endgame" not in bd:
        return _insufficient("Not enough analysed endgame moves yet.")
    prog = progress(session, user_id, 50)
    end = bd["endgame"]
    note = ""
    if prog.get("has_data"):
        note = f" Recent-window overall ACPL is {prog['recent'].get('avg_acpl')} vs previous {prog['previous'].get('avg_acpl')}."
    return {
        "answer": f"Your endgame ACPL is {end['acpl']} with {end['blunders_per_100']} blunders per 100 moves.{note}",
        "evidence": [{"endgame": end}, {"progress": prog.get("recent")}],
        "insufficient": False,
    }


def _practice(session: Session, user_id: int) -> dict:
    plan = build_plan(session, user_id)
    if not plan.items:
        return _insufficient("Not enough analysed games to build a plan yet.")
    lines = "; ".join(f"{i['title']} ({i['minutes']} min)" for i in plan.items)
    return {
        "answer": f"Suggested weekly training plan ({plan.minutes_budget} min total): {lines}.",
        "evidence": [{"recommendations": plan.items}],
        "insufficient": False,
    }
