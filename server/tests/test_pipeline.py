"""End-to-end: engine analysis -> stored evaluations -> statistics."""
from sqlalchemy import select

from app.analysis.clock import clock_report
from app.analysis.pipeline import terminal_eval
from app.analysis.stats import dashboard, move_breakdown
from app.analysis.training import build_plan, generate_puzzles, weakness_report
from app.models import EngineEvaluation, Game, GameMove


def test_terminal_eval_checkmate():
    # Black is checkmated (fool's mate position).
    fen = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
    t = terminal_eval(fen)
    assert t is not None and t["mate"] == -1  # white to move is mated


def test_terminal_eval_stalemate():
    fen = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    t = terminal_eval(fen)
    assert t is not None and t["cp"] == 0


def test_analysis_produces_persisted_evals(session, analyzed_game_id):
    game = session.get(Game, analyzed_game_id)
    assert game.analysis_status == "done"
    moves = session.scalars(
        select(GameMove).where(GameMove.game_id == analyzed_game_id).order_by(GameMove.ply)
    ).all()
    assert len(moves) == 7
    # Every move has a classification and provenance.
    assert all(m.classification for m in moves)
    evals = session.scalars(
        select(EngineEvaluation).where(EngineEvaluation.game_id == analyzed_game_id)
    ).all()
    assert len(evals) >= 5
    assert all(e.engine_name for e in evals)


def test_blunder_and_perspective(session, analyzed_game_id):
    moves = session.scalars(
        select(GameMove).where(GameMove.game_id == analyzed_game_id).order_by(GameMove.ply)
    ).all()
    nf6 = [m for m in moves if m.san == "Nf6"][0]
    assert nf6.color == "black"
    assert nf6.classification == "blunder"
    # Evaluation is stored from WHITE's point of view: white is now mating.
    assert nf6.eval_mate_in == 1 or (nf6.eval_cp is not None and nf6.eval_cp > 500)


def test_game_summary_and_dashboard(session, analyzed_game_id):
    game = session.get(Game, analyzed_game_id)
    assert game.blunders >= 1
    assert game.acpl is not None

    user_id = game.user_id
    dash = dashboard(session, user_id)
    assert dash["totals"]["games"] >= 2
    assert dash["analysis"]["done"] >= 1

    bd = move_breakdown(session, user_id)
    assert "by_phase" in bd and "by_color" in bd


def test_clock_report_derives_thinking_time(session, analyzed_game_id):
    game = session.get(Game, analyzed_game_id)
    rep = clock_report(session, game.user_id)
    assert rep["has_data"] is True
    assert rep["games_with_clock"] >= 1


def test_weaknesses_and_training(session, analyzed_game_id):
    from app.analysis.tactics import detect_tactics
    from app.models import TacticalEvent

    game = session.get(Game, analyzed_game_id)
    n_tactics = detect_tactics(session, analyzed_game_id)
    events = session.scalars(
        select(TacticalEvent).where(TacticalEvent.game_id == analyzed_game_id)
    ).all()
    # The black blunder (Nf6??) allowed a forced mate, which must be recorded.
    assert any(e.motif == "allowed_mate" and e.kind == "missed" for e in events)
    assert n_tactics >= 1

    ws = weakness_report(session, game.user_id)
    assert isinstance(ws, list)
    n = generate_puzzles(session, game.user_id, 10)
    assert n >= 1
    plan = build_plan(session, game.user_id, 90)
    assert plan.minutes_budget == 90
