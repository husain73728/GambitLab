"""Move classification and evaluation math.

All rules are documented here and covered by tests. Evaluations are stored in
centipawns from WHITE's point of view; mate is stored as signed moves-to-mate
from WHITE's point of view. Loss/severity is computed from the MOVER's view.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import chess

WIN_CP_CAP = 1000          # clamp for loss math
MISSED_WIN_CP = 200        # mover was clearly winning at/above this
STILL_WINNING_CP = 100     # ...and still winning at/above this, no "missed win"
PROVISIONAL_DEPTH = 14     # analyses shallower than this are marked provisional

# Centipawn-loss thresholds (mover POV).
T_BEST = 10
T_EXCELLENT = 25
T_GOOD = 50
T_INACCURACY = 100
T_MISTAKE = 250

CLASS_ORDER = [
    "best", "excellent", "good", "inaccuracy", "mistake", "blunder",
    "missed_win", "missed_mate", "forced", "book",
]

SEVERITY = {  # for stats/aggregation
    "best": 0, "excellent": 0, "good": 1, "inaccuracy": 2,
    "mistake": 3, "blunder": 4, "missed_win": 4, "missed_mate": 4,
    "forced": 0, "book": 0,
}


@dataclass
class MoveAssessment:
    cp_loss: int
    classification: str
    provisional: bool
    is_best: bool
    missed_win: bool
    missed_mate: bool
    explanation: str
    eff_before: int
    eff_after: int


def clamp(v: int, lo: int = -WIN_CP_CAP, hi: int = WIN_CP_CAP) -> int:
    return max(lo, min(hi, v))


def effective_cp(cp: Optional[int], mate: Optional[int], mover_is_white: bool) -> int:
    """Numeric, mover-POV evaluation clamped to the win cap. Mate dominates."""
    sign = 1 if mover_is_white else -1
    if mate is not None:
        return WIN_CP_CAP if mate * sign > 0 else -WIN_CP_CAP
    return clamp((cp or 0) * sign)


def win_percent(cp: int) -> float:
    """Lichess-style win probability from a centipawn score (mover POV)."""
    cp = clamp(cp, -2000, 2000)
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * cp)) - 1.0)


def accuracy_from_winpct(before: float, after: float) -> float:
    """Lichess-style per-move accuracy from win% drop."""
    acc = 103.1668 * math.exp(-0.04354 * (before - after)) - 3.1669
    return max(0.0, min(100.0, acc))


def classify(
    *,
    before_cp: Optional[int],
    before_mate: Optional[int],
    after_cp: Optional[int],
    after_mate: Optional[int],
    mover_is_white: bool,
    played_uci: str,
    best_uci: Optional[str],
    only_move: bool = False,
    book: bool = False,
    depth: int = 20,
    best_pv: Optional[list[str]] = None,
    fen_before: Optional[str] = None,
) -> MoveAssessment:
    """Classify one played move. Position-aware, mate-aware, provenance-aware."""
    eff_before = effective_cp(before_cp, before_mate, mover_is_white)
    eff_after = effective_cp(after_cp, after_mate, mover_is_white)

    if only_move:
        return MoveAssessment(0, "forced", False, False, False, False, "Only legal move.", eff_before, eff_after)

    # Mate bookkeeping from the mover's perspective.
    mate_before = None if before_mate is None else before_mate * (1 if mover_is_white else -1)
    mate_after = None if after_mate is None else after_mate * (1 if mover_is_white else -1)
    had_mate = mate_before is not None and mate_before > 0
    keeps_mate = mate_after is not None and mate_after > 0
    missed_mate = had_mate and not keeps_mate

    loss = max(0, eff_before - eff_after)
    is_best_move = best_uci is not None and played_uci == best_uci

    # Position-aware severity: don't call it a blunder if the game is already decided.
    downgrades = 0
    notes: list[str] = []
    if eff_before >= MISSED_WIN_CP and eff_after >= 100:
        downgrades += 1
        notes.append("still winning")
    if eff_before <= -MISSED_WIN_CP and eff_after <= -100:
        downgrades += 1
        notes.append("already lost")

    missed_win = eff_before >= MISSED_WIN_CP and eff_after < STILL_WINNING_CP

    if missed_mate:
        classification = "missed_mate"
    elif missed_win:
        classification = "missed_win"
    elif loss <= T_BEST:
        classification = "best"
    elif book and loss <= T_GOOD:
        classification = "book"
    elif loss <= T_EXCELLENT:
        classification = "excellent"
    elif loss <= T_GOOD:
        classification = "good"
    elif loss <= T_INACCURACY:
        classification = "inaccuracy"
    elif loss <= T_MISTAKE:
        classification = "mistake"
    else:
        classification = "blunder"

    # Apply downgrades for already-decided positions (never below "good").
    if downgrades and classification in ("blunder", "mistake", "missed_win"):
        order = ["best", "excellent", "good", "inaccuracy", "mistake", "blunder"]
        idx = order.index(classification if classification in order else "blunder")
        classification = order[max(0, idx - downgrades)]

    provisional = depth < PROVISIONAL_DEPTH

    explanation = build_explanation(
        classification, missed_mate, missed_win, loss, best_uci,
        mover_is_white, depth, best_pv, fen_before, notes,
    )

    return MoveAssessment(
        cp_loss=loss,
        classification=classification,
        provisional=provisional,
        is_best=is_best_move or classification == "best",
        missed_win=missed_win,
        missed_mate=missed_mate,
        explanation=explanation,
        eff_before=eff_before,
        eff_after=eff_after,
    )


def losses_win(before: int, after: int) -> bool:  # kept for readability/intent
    return before >= MISSED_WIN_CP and after < STILL_WINNING_CP


def pv_to_san(fen: str, pv_uci: list[str], max_plies: int = 6) -> str:
    """Convert a UCI principal variation to a SAN line for explanations."""
    try:
        board = chess.Board(fen)
    except Exception:
        return ""
    parts: list[str] = []
    for i, u in enumerate(pv_uci[:max_plies]):
        try:
            move = chess.Move.from_uci(u)
            if move not in board.legal_moves:
                break
            san = board.san(move)
            parts.append(san if board.turn == chess.WHITE else f"{board.fullmove_number}...{san}"
                         if i == 0 else san)
            board.push(move)
        except Exception:
            break
    return " ".join(parts)


def build_explanation(
    classification: str,
    missed_mate: bool,
    missed_win: bool,
    loss: int,
    best_uci: Optional[str],
    mover_is_white: bool,
    depth: int,
    best_pv: Optional[list[str]],
    fen_before: Optional[str],
    notes: list[str],
) -> str:
    pv_san = pv_to_san(fen_before, best_pv or []) if fen_before and best_pv else ""
    line = f" (best line: {pv_san})" if pv_san else ""
    best_txt = best_uci or "?"

    if classification == "forced":
        return "Only legal move."
    if missed_mate:
        return f"Missed a forced mate; the engine line is {best_txt}{line}."
    if missed_win:
        return f"Missed a winning continuation {best_txt}{line}; the advantage was thrown away."
    if classification in ("blunder", "mistake"):
        return f"{'Blunder' if classification == 'blunder' else 'Mistake'}, {loss}cp lost. Better was {best_txt}{line}."
    if classification == "inaccuracy":
        return f"Inaccuracy, {loss}cp lost. Engine preferred {best_txt}{line}."
    if classification == "best":
        return "Best move."
    extra = f" ({', '.join(notes)})" if notes else ""
    return f"{classification.capitalize()}{extra}."
