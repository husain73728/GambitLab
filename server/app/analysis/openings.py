"""Opening explorer and repertoire tracking."""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Optional

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Game, RepertoireLine

MIN_SAMPLE = 5  # below this, treat opening results as inconclusive


def opening_report(session: Session, user_id: int, days: Optional[int] = None,
                   color: Optional[str] = None) -> dict:
    q = select(Game).where(Game.user_id == user_id, Game.player_result.is_not(None))
    if days:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        q = q.where(Game.end_time >= since)
    if color:
        q = q.where(Game.player_color == color)
    games = list(session.scalars(q))

    groups: dict[str, dict] = defaultdict(
        lambda: {"games": 0, "wins": 0, "losses": 0, "draws": 0, "ecos": set(),
                 "colors": defaultdict(int), "time_classes": defaultdict(int),
                 "opp_ratings": [], "acpl": []}
    )
    for g in games:
        name = g.opening_name or "Unknown opening"
        grp = groups[name]
        grp["games"] += 1
        grp["wins"] += int(g.player_result == "win")
        grp["losses"] += int(g.player_result == "loss")
        grp["draws"] += int(g.player_result == "draw")
        if g.eco:
            grp["ecos"].add(g.eco)
        grp["colors"][g.player_color or "?"] += 1
        grp["time_classes"][g.time_class or "?"] += 1
        if g.opponent_rating:
            grp["opp_ratings"].append(g.opponent_rating)
        if g.acpl is not None:
            grp["acpl"].append(g.acpl)

    out = []
    for name, grp in groups.items():
        n = grp["games"]
        out.append({
            "opening": name,
            "eco": sorted(grp["ecos"])[0] if grp["ecos"] else None,
            "games": n,
            "wins": grp["wins"], "losses": grp["losses"], "draws": grp["draws"],
            "win_rate": round(100.0 * grp["wins"] / n, 1),
            "score_rate": round(100.0 * (grp["wins"] + 0.5 * grp["draws"]) / n, 1),
            "colors": dict(grp["colors"]),
            "time_classes": dict(grp["time_classes"]),
            "avg_opponent_rating": round(sum(grp["opp_ratings"]) / len(grp["opp_ratings"])) if grp["opp_ratings"] else None,
            "avg_acpl": round(sum(grp["acpl"]) / len(grp["acpl"]), 1) if grp["acpl"] else None,
            "sample_warning": n < MIN_SAMPLE,
        })
    out.sort(key=lambda o: o["games"], reverse=True)
    return {
        "openings": out,
        "note": f"Openings with fewer than {MIN_SAMPLE} games are marked as inconclusive.",
    }


def _line_moves(db: Session, user_id: int) -> list[RepertoireLine]:
    return list(session.scalars(select(RepertoireLine).where(RepertoireLine.user_id == user_id)))


def repertoire_report(session: Session, user_id: int) -> dict:
    lines = _line_moves(session, user_id)
    out = []
    for line in lines:
        out.append({
            "id": line.id, "name": line.name, "color": line.color,
            "moves_uci": line.moves_uci, "checkpoints": line.checkpoints,
        })
    return {"lines": out}


def compare_to_repertoire(session: Session, user_id: int, game_id: int) -> dict:
    """Where the player deviated from a saved repertoire line."""
    game = session.get(Game, game_id)
    if game is None:
        return {"deviations": [], "matched_plpy": 0}
    lines = [l for l in _line_moves(session, user_id) if l.color == (game.player_color or "")]
    played = _game_uci(game)
    best = {"matched": 0, "line": None, "deviation_ply": None}
    for line in lines:
        matched = 0
        for i, u in enumerate(line.moves_uci):
            if i < len(played) and played[i] == u:
                matched += 1
            else:
                break
        if matched > best["matched"]:
            best = {"matched": matched, "line": line.name, "deviation_ply": matched}
    return {
        "game_id": game_id,
        "matched_plies": best["matched"],
        "repertoire": best["line"],
        "deviation": ({"ply": best["deviation_ply"] + 1,
                       "played": played[best["deviation_ply"]] if best["deviation_ply"] < len(played) else None}
                      if best["line"] and best["deviation_ply"] is not None else None),
    }


def _game_uci(game: Game) -> list[str]:
    import chess.pgn
    import io
    g = chess.pgn.read_game(io.StringIO(game.raw_pgn))
    if g is None:
        return []
    return [n.move.uci() for n in g.mainline() if n.move]
