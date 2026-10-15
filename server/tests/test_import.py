"""Import, dedupe, opening + clock derivation."""
from sqlalchemy import select

from app.chessutil import infer_time_class, opening_from_headers, parse_pgn
from app.importer import import_pgn_text
from app.models import Game, GameMove
from tests.conftest import DRAW_PGN, SAMPLE_PGN


def test_parse_and_opening(session):
    g = parse_pgn(SAMPLE_PGN)
    assert g is not None
    eco, name = opening_from_headers(g.headers)
    assert eco == "C20"
    assert "Kings Pawn" in name


def test_time_class_inference():
    assert infer_time_class("60") == "bullet"
    assert infer_time_class("300") == "blitz"
    assert infer_time_class("600") == "rapid"
    assert infer_time_class("1/259200") == "daily"
    assert infer_time_class("-") is None


def test_import_is_idempotent(session):
    from app.deps import get_current_user

    unique = """[Event "Idem"]
[White "Ida"]
[Black "Jon"]
[Result "1-0"]
[TimeControl "600"]
[UTCDate "2024.03.03"]

1. d4 d5 2. c4 e6 1-0
"""
    user = get_current_user(session)
    first, _ = import_pgn_text(session, user.id, unique, username="Ida", enqueue=False)
    session.commit()
    second, skipped = import_pgn_text(session, user.id, unique, username="Ida", enqueue=False)
    session.commit()
    assert first == 1
    assert second == 0 and skipped == 1  # duplicate detected


def test_player_perspective_and_result(session, imported_game_id):
    g = session.get(Game, imported_game_id)
    assert g.player_color == "black"
    assert g.player_result == "loss"
    assert g.opponent_username == "Alice"
    assert g.opponent_rating == 1500
    assert g.move_count == 7


def test_clock_data_preserved(session, imported_game_id):
    moves = session.scalars(
        select(GameMove).where(GameMove.game_id == imported_game_id).order_by(GameMove.ply)
    ).all()
    assert moves[0].clock_seconds == 598
    assert all(m.fen_before and m.fen_after for m in moves)


def test_malformed_pgn_is_safe(session):
    from app.deps import get_current_user

    user = get_current_user(session)
    imported, skipped = import_pgn_text(session, user.id, "this is not a pgn", username="X", enqueue=False)
    assert imported == 0
