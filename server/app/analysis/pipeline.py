"""Multi-stage analysis pipeline with caching, checkpointing and provenance."""
from __future__ import annotations

import hashlib
import time
from typing import Optional

import chess
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DEEP_DEPTH, FAST_DEPTH, MULTIPV
from ..engine.manager import get_secondary_config, manager
from ..engine.uci import EngineError
from ..models import EngineConfig, EngineEvaluation, Game, GameMove, PositionEval
from .classify import accuracy_from_winpct, classify, win_percent

BOOK_PLIES = 8


def _cache_key(fen: str, engine_name: str, version: Optional[str], multipv: int) -> str:
    return hashlib.sha256(f"{fen}|{engine_name}|{version}|{multipv}".encode()).hexdigest()


def terminal_eval(fen: str) -> Optional[dict]:
    """Deterministic evaluation for game-over positions (no engine needed)."""
    try:
        board = chess.Board(fen)
    except Exception:
        return None
    if board.is_checkmate():
        # The side to move is mated; the winner delivered mate in 1 (white POV).
        mate = -1 if board.turn == chess.WHITE else 1
        return {"cp": None, "mate": mate, "best": None, "pv": [], "multipv": [],
                "depth": 0, "nodes": 0, "cached": False, "terminal": True}
    if (board.is_stalemate() or board.is_insufficient_material()
            or board.is_seventyfive_moves() or board.is_fivefold_repetition()):
        return {"cp": 0, "mate": None, "best": None, "pv": [], "multipv": [],
                "depth": 0, "nodes": 0, "cached": False, "terminal": True}
    return None


def evaluate_position(
    session: Session,
    cfg: EngineConfig,
    fen: str,
    depth: int,
    multipv: int = 1,
    game_id: Optional[int] = None,
    ply: Optional[int] = None,
    kind: str = "primary",
) -> dict:
    """Evaluate a position, using the persistent cache when possible."""
    term = terminal_eval(fen)
    if term is not None:
        return term

    version = cfg.version
    key = _cache_key(fen, cfg.name, version, multipv)
    cached = session.scalar(select(PositionEval).where(PositionEval.cache_key == key))
    if cached is not None and cached.depth >= depth:
        return {
            "cp": cached.score_cp, "mate": cached.mate_in, "best": cached.best_uci,
            "pv": (cached.multipv[0]["pv"] if cached.multipv else []),
            "multipv": cached.multipv, "depth": cached.depth, "nodes": cached.nodes,
            "cached": True,
        }

    last_err: Optional[Exception] = None
    for attempt in range(2):
        try:
            engine = manager.acquire(cfg)
            lines = engine.analyse(fen, depth=depth, multipv=multipv)
            cfg.version = engine.version  # capture provenance
            break
        except EngineError as exc:
            last_err = exc
            manager.drop(cfg)
    else:
        raise EngineError(f"engine failed after retries: {last_err}")

    top = lines[0] if lines else None
    mpv = [
        {"rank": l.rank, "uci": l.uci, "cp": l.cp, "mate": l.mate, "pv": l.pv}
        for l in lines
    ]
    record = PositionEval(
        cache_key=key,
        fen=fen,
        engine_name=cfg.name,
        engine_version=version,
        depth=depth,
        multipv=mpv,
        best_uci=top.uci if top else None,
        score_cp=top.cp if top else None,
        mate_in=top.mate if top else None,
        nodes=top.nodes if top else None,
        time_ms=None,
    )
    # upsert
    if cached is not None:
        cached.depth = depth
        cached.multipv = mpv
        cached.best_uci = record.best_uci
        cached.score_cp = record.score_cp
        cached.mate_in = record.mate_in
        cached.nodes = record.nodes
    else:
        session.add(record)

    session.add(EngineEvaluation(
        game_id=game_id, ply=ply, fen=fen,
        engine_name=cfg.name, engine_version=version, kind=kind,
        depth=depth, multipv=multipv,
        score_cp=record.score_cp, mate_in=record.mate_in,
        best_uci=record.best_uci, pv=mpv,
        nodes=record.nodes,
        settings={"threads": cfg.threads, "hash": cfg.hash_mb, "multipv": multipv},
    ))
    session.flush()

    return {
        "cp": record.score_cp, "mate": record.mate_in, "best": record.best_uci,
        "pv": mpv[0]["pv"] if mpv else [], "multipv": mpv,
        "depth": depth, "nodes": record.nodes, "cached": False,
    }


def _legal_count(fen: str) -> int:
    try:
        return chess.Board(fen).legal_moves.count()
    except Exception:
        return 1


def _critical(assessment_class: str, eff_before: int, eff_after: int) -> bool:
    if assessment_class in ("blunder", "mistake", "missed_win", "missed_mate"):
        return True
    return abs(eff_before - eff_after) >= 150


def run_analysis(
    session: Session,
    game_id: int,
    cfg: Optional[EngineConfig] = None,
    job=None,
    fast_depth: int = FAST_DEPTH,
    deep_depth: int = DEEP_DEPTH,
    use_secondary: bool = False,
) -> dict:
    """Analyse a whole game: fast scan -> deep pass on critical positions."""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"game {game_id} not found")

    if cfg is None:
        from ..engine.manager import get_primary_config
        cfg = get_primary_config(session)

    moves: list[GameMove] = list(session.scalars(
        select(GameMove).where(GameMove.game_id == game_id).order_by(GameMove.ply)
    ))
    if not moves:
        game.analysis_status = "done"
        game.analysis_progress = 100
        session.commit()
        return {"game_id": game_id, "moves": 0}

    game.analysis_status = "analyzing"
    session.commit()

    # Positions p_0 .. p_N  (before each move, then final position).
    fens = [m.fen_before for m in moves] + [moves[-1].fen_after]
    total_steps = len(fens)
    evals: list[dict] = [None] * len(fens)  # type: ignore

    start = time.time()
    for k, fen in enumerate(fens):
        evals[k] = evaluate_position(session, cfg, fen, fast_depth, multipv=1,
                                     game_id=game_id, ply=(k + 1 if k < len(moves) else None))
        if job is not None:
            job.progress = int(100 * (k + 1) / total_steps * 0.6)
            job.checkpoint_ply = k
        game.analysis_progress = int(100 * (k + 1) / total_steps * 0.6)
        if k % 5 == 0:
            session.commit()

    # Stage A classification.
    assessments = []
    for i, mv in enumerate(moves):
        before, after = evals[i], evals[i + 1]
        mover_white = mv.color == "white"
        a = classify(
            before_cp=before["cp"], before_mate=before["mate"],
            after_cp=after["cp"], after_mate=after["mate"],
            mover_is_white=mover_white,
            played_uci=mv.uci, best_uci=before["best"],
            only_move=_legal_count(mv.fen_before) == 1,
            book=(i < BOOK_PLIES),
            depth=fast_depth,
            best_pv=before["pv"], fen_before=mv.fen_before,
        )
        assessments.append(a)

    # Stage B: deep re-analysis of critical positions.
    if deep_depth > fast_depth:
        for i, mv in enumerate(moves):
            a = assessments[i]
            if not _critical(a.classification, a.eff_before, a.eff_after):
                continue
            deep = evaluate_position(session, cfg, mv.fen_before, deep_depth, multipv=MULTIPV,
                                     game_id=game_id, ply=mv.ply)
            nxt = evals[i + 1]
            a2 = classify(
                before_cp=deep["cp"], before_mate=deep["mate"],
                after_cp=nxt["cp"], after_mate=nxt["mate"],
                mover_is_white=(mv.color == "white"),
                played_uci=mv.uci, best_uci=deep["best"],
                only_move=_legal_count(mv.fen_before) == 1,
                book=(i < BOOK_PLIES),
                depth=deep_depth,
                best_pv=deep["pv"], fen_before=mv.fen_before,
            )
            assessments[i] = a2
            evals[i] = deep
            if job is not None:
                job.progress = 60 + int(40 * (i + 1) / len(moves))
            session.commit()

    # Persist per-move results.
    for i, mv in enumerate(moves):
        before, after = evals[i], evals[i + 1]
        a = assessments[i]
        mv.eval_cp = after["cp"]
        mv.eval_mate_in = after["mate"]
        mv.best_eval_cp = before["cp"]
        mv.best_mate_in = before["mate"]
        mv.best_uci = before["best"]
        mv.cp_loss = a.cp_loss
        mv.classification = a.classification
        mv.provisional = a.provisional
        mv.alternatives = before.get("multipv", [])[:MULTIPV]
        mv.explanation = a.explanation

    _update_game_summary(session, game, moves, assessments)
    game.analysis_status = "done"
    game.analysis_progress = 100
    if job is not None:
        job.status = "done"
        job.stage = "done"
        job.progress = 100
        job.engine_name = cfg.name
        job.engine_version = cfg.version
    session.commit()

    if use_secondary:
        try:
            run_secondary_pass(session, game_id, moves, assessments)
        except Exception:
            pass

    from .stats import invalidate_stats
    invalidate_stats(session, game.user_id)

    elapsed = time.time() - start
    return {"game_id": game_id, "moves": len(moves), "seconds": round(elapsed, 2)}


def run_secondary_pass(session: Session, game_id: int, moves: list[GameMove], assessments) -> int:
    """Independent evaluation of critical positions with the secondary engine."""
    cfg = get_secondary_config(session)
    if cfg is None:
        return 0
    count = 0
    for i, mv in enumerate(moves):
        a = assessments[i]
        if a.classification not in ("blunder", "mistake", "missed_win", "missed_mate"):
            continue
        evaluate_position(session, cfg, mv.fen_before, cfg.depth, multipv=1,
                          game_id=game_id, ply=mv.ply, kind="secondary")
        count += 1
    session.commit()
    return count


def _update_game_summary(session: Session, game: Game, moves: list[GameMove], assessments) -> None:
    is_player_white = game.player_color == "white"
    is_player_black = game.player_color == "black"

    def relevant(mv: GameMove) -> bool:
        if game.player_color is None:
            return True
        return mv.color == game.player_color
    _ = (is_player_white, is_player_black, relevant)

    losses: list[int] = []
    accs: list[float] = []
    counts = {"blunder": 0, "mistake": 0, "inaccuracy": 0}
    best_count = 0
    missed_win = missed_mate = 0
    tp_err = 0
    total = 0

    for i, (mv, a) in enumerate(zip(moves, assessments)):
        if game.player_color is not None and mv.color != game.player_color:
            continue
        total += 1
        if a.classification in ("forced", "book"):
            continue
        losses.append(a.cp_loss)
        before_wp = win_percent(a.eff_before)
        after_wp = win_percent(a.eff_after)
        accs.append(accuracy_from_winpct(before_wp, after_wp))
        if a.classification in counts:
            counts[a.classification] += 1
        if a.is_best:
            best_count += 1
        missed_win += int(a.missed_win)
        missed_mate += int(a.missed_mate)
        if a.classification in ("blunder", "mistake") and mv.clock_seconds is not None and mv.clock_seconds <= 10:
            tp_err += 1

    game.acpl = round(sum(losses) / len(losses), 1) if losses else None
    game.accuracy = round(sum(accs) / len(accs), 1) if accs else None
    game.best_move_rate = round(100.0 * best_count / total, 1) if total else None
    game.blunders = counts["blunder"]
    game.mistakes = counts["mistake"]
    game.inaccuracies = counts["inaccuracy"]
    game.missed_wins = missed_win
    game.missed_mates = missed_mate
    game.time_pressure_errors = tp_err


def compute_acpl_series(moves: list[GameMove]) -> list[Optional[int]]:
    """Eval after each move (white POV) for the evaluation graph."""
    return [m.eval_cp for m in moves]
