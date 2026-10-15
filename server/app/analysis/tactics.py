"""Tactical motif detection grounded in real positions and engine lines.

Only motifs we can verify from the board are asserted; each event carries a
confidence and the concrete board state. Uncertain heuristics are skipped.
"""
from __future__ import annotations

from typing import Optional

import chess
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Game, GameMove, TacticalEvent

VALUES = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100,
}
MOTIF_LABELS = {
    "fork": "Fork",
    "pin": "Pin",
    "skewer": "Skewer",
    "discovered_attack": "Discovered attack",
    "hanging_piece": "Hanging piece",
    "back_rank": "Back-rank weakness",
    "missed_check": "Missed check",
    "missed_capture": "Missed capture",
    "mate": "Mating pattern",
    "allowed_mate": "Allowed mate",
    "removing_defender": "Removing the defender",
}


def _val(pc: Optional[chess.Piece]) -> int:
    return VALUES.get(pc.piece_type, 0) if pc else 0


def detect_after(board_before: chess.Board, move: chess.Move) -> list[tuple[str, dict, float]]:
    """Motifs created BY the move."""
    found: list[tuple[str, dict, float]] = []
    board = board_before.copy(stack=False)
    if move not in board.legal_moves:
        return found
    mover = board.turn
    enemy = not mover
    board.push(move)
    to = move.to_square
    piece = board.piece_at(to)
    if piece is None:
        return found

    attacked = board.attacks(to)
    targets = []
    for sq in chess.scan_reversed(attacked & board.occupied_co[enemy]):
        pc = board.piece_at(sq)
        if pc:
            targets.append((sq, pc))
    if len(targets) >= 2:
        found.append(("fork", {"square": chess.square_name(to),
                               "targets": [chess.square_name(s) for s, _ in targets]}, 0.85))
    king_sq = board.king(enemy)
    if king_sq is not None and any(s == king_sq for s, _ in targets):
        others = [s for s, _ in targets if s != king_sq]
        if others:
            found.append(("fork", {"square": chess.square_name(to), "check": True,
                                   "targets": [chess.square_name(s) for s in others],
                                   "royal": True}, 0.9))

    # Pins / skewers on the ray from the moved piece.
    for sq, pc in targets:
        if pc.piece_type == chess.KING:
            continue
        if board.is_pinned(enemy, sq):
            found.append(("pin", {"square": chess.square_name(to),
                                  "pinned": chess.square_name(sq)}, 0.8))
        # skewer: a higher-value piece in front, lower-value behind on the same ray
        for ray_dir in (1, -1):
            behind = _piece_behind(board, to, sq, ray_dir)
            if behind and _val(behind[1]) < _val(pc):
                found.append(("skewer", {"square": chess.square_name(to),
                                         "front": chess.square_name(sq),
                                         "behind": chess.square_name(behind[0])}, 0.7))
                break

    # Discovered attack: a friendly slider now attacks through the vacated square.
    from_sq = move.from_square
    for sq in chess.SQUARES:
        p = board.piece_at(sq)
        if p and p.color == mover and p.piece_type in (chess.BISHOP, chess.ROOK, chess.QUEEN):
            if sq == to:
                continue
            for attacked_sq in chess.scan_reversed(board.attacks(sq) & board.occupied_co[enemy]):
                if _between_contains(sq, attacked_sq, from_sq) and _val(board.piece_at(attacked_sq)) >= 3:
                    found.append(("discovered_attack", {
                        "slider": chess.square_name(sq),
                        "target": chess.square_name(attacked_sq),
                    }, 0.6))
                    break

    # Back-rank mate.
    if board.is_checkmate() and _is_back_rank(board, enemy):
        found.append(("back_rank", {"mate": True, "square": chess.square_name(to)}, 0.75))

    return found


def _is_back_rank(board: chess.Board, color: chess.Color) -> bool:
    king_sq = board.king(color)
    if king_sq is None:
        return False
    rank = chess.square_rank(king_sq)
    return rank in (0, 7)


def _piece_behind(board: chess.Board, a: int, b: int, _dir: int):
    """First piece beyond b continuing the a->b ray."""
    ar, ac = divmod(a, 8)
    br, bc = divmod(b, 8)
    dr = (br > ar) - (br < ar)
    dc = (bc > ac) - (bc < ac)
    r, c = br + dr, bc + dc
    while 0 <= r < 8 and 0 <= c < 8:
        sq = r * 8 + c
        pc = board.piece_at(sq)
        if pc:
            return sq, pc
        r += dr
        c += dc
    return None


def _between_contains(a: int, b: int, sq: int) -> bool:
    ar, ac = divmod(a, 8)
    br, bc = divmod(b, 8)
    dr = (br > ar) - (br < ar)
    dc = (bc > ac) - (bc < ac)
    if dr and dc and abs(br - ar) != abs(bc - ac):
        return False
    r, c = ar + dr, ac + dc
    while (r, c) != (br, bc):
        if r == br and c == bc:
            break
        if r * 8 + c == sq:
            return True
        r += dr
        c += dc
        if not (0 <= r < 8 and 0 <= c < 8):
            return False
    return False


def detect_opportunity(board_before: chess.Board) -> list[tuple[str, dict, float]]:
    """Motifs available to the side to move (e.g. a hanging enemy piece)."""
    found: list[tuple[str, dict, float]] = []
    mover = board_before.turn
    for sq in chess.SQUARES:
        pc = board_before.piece_at(sq)
        if pc is None or pc.color == mover:
            continue
        attackers = board_before.attackers(mover, sq)
        if not attackers:
            continue
        defenders = board_before.attackers(not mover, sq)
        if not defenders and _val(pc) >= 3:
            found.append(("hanging_piece", {
                "square": chess.square_name(sq),
                "piece": pc.symbol(),
            }, 0.7))
    return found


def detect_tactics(session: Session, game_id: int, min_loss: int = 100) -> int:
    """Detect and persist tactical events for the player's analysed moves."""
    game = session.get(Game, game_id)
    if game is None or game.player_color is None:
        return 0
    session.execute(delete(TacticalEvent).where(TacticalEvent.game_id == game_id))

    moves = session.scalars(
        select(GameMove).where(GameMove.game_id == game_id).order_by(GameMove.ply)
    ).all()

    count = 0
    for mv in moves:
        if mv.color != game.player_color or not mv.classification:
            continue
        try:
            board = chess.Board(mv.fen_before)
        except Exception:
            continue

        # Tactics the player actually found (a good move that creates a motif).
        if mv.classification in ("best", "excellent") and mv.uci:
            for motif, detail, conf in detect_after(board, chess.Move.from_uci(mv.uci)):
                session.add(TacticalEvent(
                    user_id=game.user_id, game_id=game_id, ply=mv.ply, motif=motif,
                    kind="found", color=mv.color, fen=mv.fen_before,
                    eval_loss_cp=0, confidence=conf, detail=detail,
                ))
                count += 1

        # Tactics missed (an error where the engine's best move made a motif).
        if mv.classification in ("inaccuracy", "mistake", "blunder", "missed_win", "missed_mate") \
                and mv.best_uci and (mv.cp_loss or 0) >= min_loss:
            # Allowed a forced mate against the player.
            mover_white = mv.color == "white"
            sign = 1 if mover_white else -1
            after_mate = mv.eval_mate_in
            before_mate = mv.best_mate_in
            mate_now_against = after_mate is not None and after_mate * sign < 0
            mate_before_against = before_mate is not None and before_mate * sign < 0
            if mate_now_against and not mate_before_against:
                session.add(TacticalEvent(
                    user_id=game.user_id, game_id=game_id, ply=mv.ply, motif="allowed_mate",
                    kind="missed", color=mv.color, fen=mv.fen_before,
                    eval_loss_cp=mv.cp_loss or 0, confidence=0.85,
                    detail={"mate_in": after_mate, "best": mv.best_uci},
                ))
                count += 1

            reason = None
            if mv.best_uci:
                bm = chess.Move.from_uci(mv.best_uci)
                motives = detect_after(board, bm)
                for motif, detail, conf in motives:
                    session.add(TacticalEvent(
                        user_id=game.user_id, game_id=game_id, ply=mv.ply, motif=motif,
                        kind="missed", color=mv.color, fen=mv.fen_before,
                        eval_loss_cp=mv.cp_loss or 0, confidence=conf, detail={**detail, "best": mv.best_uci},
                    ))
                    count += 1
                if not motives:
                    reason = _classify_simple(board, bm)
                    if reason:
                        session.add(TacticalEvent(
                            user_id=game.user_id, game_id=game_id, ply=mv.ply, motif=reason[0],
                            kind="missed", color=mv.color, fen=mv.fen_before,
                            eval_loss_cp=mv.cp_loss or 0, confidence=reason[2],
                            detail={**reason[1], "best": mv.best_uci},
                        ))
                        count += 1
            _ = reason

            # Hanging pieces available before the error.
            for motif, detail, conf in detect_opportunity(board):
                session.add(TacticalEvent(
                    user_id=game.user_id, game_id=game_id, ply=mv.ply, motif=motif,
                    kind="missed", color=mv.color, fen=mv.fen_before,
                    eval_loss_cp=mv.cp_loss or 0, confidence=conf,
                    detail={**detail, "best": mv.best_uci},
                ))
                count += 1

    game.tactical_events_count = count
    session.commit()
    return count


def _classify_simple(board: chess.Board, best: chess.Move):
    if best not in board.legal_moves:
        return None
    if board.gives_check(best):
        return ("missed_check", {"best": best.uci()}, 0.45)
    if board.is_capture(best):
        victim = board.piece_at(best.to_square)
        return ("missed_capture", {"best": best.uci(),
                                   "victim": victim.symbol() if victim else "?"}, 0.5)
    return None
