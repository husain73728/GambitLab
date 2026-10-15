"""Chess-specific parsing helpers built on python-chess."""
from __future__ import annotations

import hashlib
import io
import re
from typing import Any, Optional

import chess
import chess.pgn

PIECE_NAMES = {"P": "pawn", "N": "knight", "B": "bishop", "R": "rook", "Q": "queen", "K": "king"}


def parse_pgn(pgn_text: str) -> Optional[chess.pgn.Game]:
    try:
        game = chess.pgn.read_game(io.StringIO(pgn_text))
    except Exception:
        return None
    return game


def iter_games(pgn_text: str):
    stream = io.StringIO(pgn_text)
    while True:
        try:
            game = chess.pgn.read_game(stream)
        except Exception:
            break
        if game is None:
            break
        yield game


def extract_moves(game: chess.pgn.Game) -> list[dict[str, Any]]:
    """Return normalized per-ply move records with FENs and clock data."""
    out: list[dict[str, Any]] = []
    board = game.board()
    for idx, node in enumerate(game.mainline(), start=1):
        move = node.move
        if move is None:
            break
        san = board.san(move)

        is_ep = board.is_en_passant(move)
        is_capture = board.is_capture(move)
        captured: Optional[str] = None
        if is_capture:
            if is_ep:
                captured = "P"
            else:
                pc = board.piece_at(move.to_square)
                captured = pc.symbol().upper() if pc else None

        fen_before = board.fen()
        board.push(move)
        fen_after = board.fen()

        clock = None
        try:
            clock = node.clock()
        except Exception:
            clock = None

        out.append(
            {
                "ply": idx,
                "move_number": (idx + 1) // 2,
                "color": "white" if idx % 2 == 1 else "black",
                "san": san,
                "uci": move.uci(),
                "fen_before": fen_before,
                "fen_after": fen_after,
                "is_capture": is_capture,
                "captured_piece": captured,
                "is_check": board.is_check(),
                "is_mate": board.is_checkmate(),
                "clock_seconds": clock,
            }
        )
    return out


_RESULT_MAP = {"1-0": ("win", "loss"), "0-1": ("loss", "win"), "1/2-1/2": ("draw", "draw")}


def result_for(white_result: Optional[str], black_result: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """Map ('win'/'loss'/'draw' per player) if given, else derive from a PGN result."""
    return white_result, black_result


def side_result(white_res: str, black_res: str, color: str) -> str:
    """Return 'win'|'loss'|'draw' for the given colour from white/black results."""
    r = white_res if color == "white" else black_res
    return {"win": "win", "loss": "loss", "draw": "draw"}.get(r, "draw")


def infer_time_class(time_control: Optional[str]) -> Optional[str]:
    """Infer bullet/blitz/rapid/daily from a PGN time control string."""
    if not time_control or time_control in ("-", "?"):
        return None
    if "/" in time_control:  # daily style like "1/259200"
        return "daily"
    m = re.match(r"^(\d+)", time_control)
    if not m:
        return None
    base = int(m.group(1))
    if base < 180:
        return "bullet"
    if base < 600:
        return "blitz"
    if base < 1800:
        return "rapid"
    return "daily"


def opening_from_headers(headers: Any) -> tuple[Optional[str], Optional[str]]:
    """Return (eco, human_readable_name)."""
    eco = headers.get("ECO") or None

    name = headers.get("Opening") or None
    if name:
        return eco, name

    url = headers.get("ECOUrl") or ""
    if url:
        slug = url.rstrip("/").split("/")[-1]
        slug = re.sub(r"\.\w+$", "", slug)  # drop .eco.html etc.
        name = slug.replace("-", " ").strip()
        if name:
            return eco, name
    return eco, None


def fingerprint(pgn_text: str) -> str:
    """Stable dedupe key for a game, independent of surrounding whitespace."""
    game = parse_pgn(pgn_text)
    if game is None:
        return hashlib.sha256(re.sub(r"\s+", " ", pgn_text).strip().encode()).hexdigest()
    h = game.headers
    moves = " ".join(n.san() for n in game.mainline())
    key = "|".join(
        [
            h.get("White", "?"),
            h.get("Black", "?"),
            h.get("Result", "*"),
            h.get("UTCDate", h.get("Date", "?")),
            h.get("UTCTime", h.get("StartTime", "?")),
            moves[:400],
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()
