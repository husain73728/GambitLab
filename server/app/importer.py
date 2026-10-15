"""Import + normalization pipeline (Chess.com API and manual PGN)."""
from __future__ import annotations

import datetime as dt
import hashlib
from typing import Any, Optional

import chess.pgn
from sqlalchemy import select
from sqlalchemy.orm import Session

from .chessutil import (
    extract_moves,
    fingerprint,
    infer_time_class,
    opening_from_headers,
    parse_pgn,
)
from .models import AnalysisJob, ConnectedAccount, Game, GameMove, ImportLog, User


def _epoch_to_dt(value: Optional[int]) -> Optional[dt.datetime]:
    if not value:
        return None
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc)


def _export_pgn(game: chess.pgn.Game) -> str:
    return game.accept(chess.pgn.StringExporter(headers=True, variations=False, comments=True))


def _pgn_datetime(headers: Any) -> Optional[dt.datetime]:
    date = headers.get("UTCDate") or headers.get("Date")
    tm = headers.get("UTCTime") or headers.get("StartTime") or "00:00:00"
    if not date or date.startswith("????"):
        return None
    try:
        y, m, d = (int(x) for x in date.split("."))
        hh, mm, ss = (int(float(x)) for x in str(tm).replace(":", " ").split())
        return dt.datetime(y, m, d, hh, mm, ss, tzinfo=dt.timezone.utc)
    except Exception:
        return None


def record_from_pgn(
    pgn_text: str,
    provider_game_id: Optional[str] = None,
    source: str = "pgn",
    username: Optional[str] = None,
    overrides: Optional[dict] = None,
) -> Optional[dict]:
    """Normalize one PGN text into a game record dict (+ moves)."""
    game = parse_pgn(pgn_text)
    if game is None:
        return None
    return record_from_game(game, provider_game_id, source, username, overrides, raw_pgn=pgn_text)


def record_from_game(
    game: chess.pgn.Game,
    provider_game_id: Optional[str] = None,
    source: str = "pgn",
    username: Optional[str] = None,
    overrides: Optional[dict] = None,
    raw_pgn: Optional[str] = None,
) -> Optional[dict]:
    """Normalize a parsed python-chess game into a record dict (+ moves)."""
    headers = game.headers
    moves = extract_moves(game)

    white = headers.get("White", "?")
    black = headers.get("Black", "?")
    result = headers.get("Result", "*")
    eco, opening = opening_from_headers(headers)

    w_res, b_res = {"1-0": ("win", "loss"), "0-1": ("loss", "win"), "1/2-1/2": ("draw", "draw")}.get(
        result, (None, None)
    )

    color = None
    if username:
        if username.lower() == white.lower():
            color = "white"
        elif username.lower() == black.lower():
            color = "black"

    if color == "white":
        player_result = w_res
        opponent = black
    elif color == "black":
        player_result = b_res
        opponent = white
    else:
        player_result = None
        opponent = None

    rec = {
        "source": source,
        "provider_game_id": provider_game_id,
        "raw_pgn": raw_pgn if raw_pgn is not None else _export_pgn(game),
        "white_username": white,
        "black_username": black,
        "white_rating": _int_or_none(headers.get("WhiteElo")),
        "black_rating": _int_or_none(headers.get("BlackElo")),
        "white_result": w_res,
        "black_result": b_res,
        "player_color": color,
        "player_result": player_result,
        "opponent_username": opponent,
        "opponent_rating": (
            _int_or_none(headers.get("BlackElo")) if color == "white"
            else _int_or_none(headers.get("WhiteElo")) if color == "black"
            else None
        ),
        "time_class": infer_time_class(headers.get("TimeControl")),
        "time_control": headers.get("TimeControl"),
        "rules": "chess",
        "rated": (headers.get("Event", "").lower().find("rated") >= 0),
        "eco": eco,
        "opening_name": opening,
        "start_time": _pgn_datetime(headers),
        "end_time": _pgn_datetime(headers),
        "termination": headers.get("Termination"),
        "move_count": len(moves),
        "has_clock_data": any(m["clock_seconds"] is not None for m in moves),
        "moves": moves,
    }

    if overrides:
        rec.update({k: v for k, v in overrides.items() if v is not None})

    if provider_game_id:
        rec["dedupe_key"] = hashlib.sha256(provider_game_id.encode()).hexdigest()
    else:
        rec["dedupe_key"] = fingerprint(rec["raw_pgn"])

    return rec


def _int_or_none(v: Any) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def enrich_from_chesscom(record: dict, raw: dict) -> dict:
    """Overlay authoritative Chess.com metadata onto a PGN-derived record."""
    white = raw.get("white", {})
    black = raw.get("black", {})
    overrides = {
        "provider_game_id": raw.get("url"),
        "white_username": white.get("username"),
        "black_username": black.get("username"),
        "white_rating": white.get("rating"),
        "black_rating": black.get("rating"),
        "time_class": raw.get("time_class"),
        "time_control": raw.get("time_control"),
        "rules": raw.get("rules", "chess"),
        "rated": raw.get("rated"),
        "end_time": _epoch_to_dt(raw.get("end_time")),
        "start_time": _epoch_to_dt(raw.get("start_time")) or record.get("start_time"),
    }
    # Chess.com result codes are already win/loss/draw strings.
    for side, key in (("white", white), ("black", black)):
        overrides[f"{side}_result"] = key.get("result")
    rec = {**record, **{k: v for k, v in overrides.items() if v is not None}}
    rec["dedupe_key"] = hashlib.sha256(str(raw.get("url")).encode()).hexdigest()
    return rec


def _recompute_player_view(rec: dict, username: Optional[str]) -> None:
    if not username:
        return
    if username.lower() == (rec.get("white_username") or "").lower():
        rec["player_color"] = "white"
        rec["player_result"] = rec.get("white_result")
        rec["opponent_username"] = rec.get("black_username")
        rec["opponent_rating"] = rec.get("black_rating")
    elif username.lower() == (rec.get("black_username") or "").lower():
        rec["player_color"] = "black"
        rec["player_result"] = rec.get("black_result")
        rec["opponent_username"] = rec.get("white_username")
        rec["opponent_rating"] = rec.get("white_rating")


def persist_game(
    session: Session,
    user_id: int,
    rec: dict,
    account_id: Optional[int] = None,
    enqueue: bool = True,
) -> tuple[Optional[Game], bool]:
    """Insert a game if not already present. Returns (game, created)."""
    existing = session.scalar(select(Game).where(Game.dedupe_key == rec["dedupe_key"]))
    if existing is not None:
        return existing, False

    moves = rec.pop("moves", [])
    game = Game(user_id=user_id, account_id=account_id, **rec)
    game.analysis_status = "imported"
    session.add(game)
    session.flush()  # assign id

    for m in moves:
        session.add(GameMove(game_id=game.id, **m))
    session.flush()  # ensure move rows are visible to later queries (autoflush is off)

    if enqueue:
        session.add(AnalysisJob(game_id=game.id, status="queued", stage="fast", priority=50))

    return game, True


def import_pgn_text(
    session: Session,
    user_id: int,
    pgn_text: str,
    account_id: Optional[int] = None,
    username: Optional[str] = None,
    enqueue: bool = True,
) -> tuple[int, int]:
    """Import every game in a (multi-game) PGN. Returns (imported, skipped)."""
    imported = skipped = 0
    import io as _io

    stream = _io.StringIO(pgn_text)
    while True:
        try:
            g = chess.pgn.read_game(stream)
        except Exception:
            break
        if g is None:
            break
        if not list(g.mainline()):
            skipped += 1
            continue
        rec = record_from_game(g, source="pgn", username=username, raw_pgn=_export_pgn(g))
        if rec is None:
            skipped += 1
            continue
        _recompute_player_view(rec, username)
        _game, created = persist_game(session, user_id, rec, account_id=account_id, enqueue=enqueue)
        imported += int(created)
        skipped += int(not created)
    session.commit()
    from .analysis.stats import invalidate_stats
    invalidate_stats(session, user_id)
    return imported, skipped


def import_chesscom_account(
    session: Session,
    account: ConnectedAccount,
    archives: Optional[list[str]] = None,
    limit_months: Optional[int] = None,
    time_classes: Optional[list[str]] = None,
    client=None,
) -> tuple[int, int]:
    """Fetch and store games for the account's selected archives."""
    from .chesscom import ChessComClient

    owned = client is None
    client = client or ChessComClient()
    imported = skipped = 0
    log = ImportLog(user_id=account.user_id, account_id=account.id, kind="chesscom", status="running")
    session.add(log)
    session.flush()
    try:
        urls = archives if archives is not None else client.archives(account.username)
        if limit_months:
            urls = urls[-limit_months:]
        for url in urls:
            try:
                games = client.monthly_games(0, 0, archive_url=url)
            except Exception as exc:  # keep going on a bad month
                log.detail = {**(log.detail or {}), "last_error": str(exc)}
                continue
            for raw in games:
                if raw.get("rules", "chess") != "chess":
                    skipped += 1
                    continue
                if time_classes and raw.get("time_class") not in time_classes:
                    skipped += 1
                    continue
                pgn = raw.get("pgn")
                if not pgn:
                    skipped += 1
                    continue
                rec = record_from_pgn(
                    pgn, provider_game_id=raw.get("url"), source="chesscom",
                    username=account.username,
                )
                if rec is None:
                    skipped += 1
                    continue
                rec = enrich_from_chesscom(rec, raw)
                _recompute_player_view(rec, account.username)
                _game, created = persist_game(
                    session, account.user_id, rec, account_id=account.id, enqueue=True
                )
                imported += int(created)
                skipped += int(not created)
            log.games_imported = imported
            log.games_skipped = skipped
            session.commit()
            from .analysis.stats import invalidate_stats
            invalidate_stats(session, account.user_id)
        log.status = "done"
        account.last_synced_at = dt.datetime.now(dt.timezone.utc)
    except Exception as exc:
        log.status = "failed"
        log.error = str(exc)
        raise
    finally:
        log.finished_at = dt.datetime.now(dt.timezone.utc)
        session.commit()
        if owned:
            client.close()
    return imported, skipped
