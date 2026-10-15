"""Pytest fixtures: isolated temp database + a shared imported game."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_TMP = pathlib.Path(tempfile.gettempdir()) / "gambitlab_test"
_TMP.mkdir(exist_ok=True)
_DB = _TMP / "test.db"
for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(str(_DB) + suffix)
    except OSError:
        pass
os.environ["GAMBITLAB_DATABASE_URL"] = "sqlite:///" + _DB.as_posix()
os.environ["GAMBITLAB_DATA_DIR"] = str(_TMP)

import pytest  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402

SAMPLE_PGN = """[Event "Test"]
[Site "chess.com"]
[White "Alice"]
[Black "Bob"]
[Result "1-0"]
[WhiteElo "1500"]
[BlackElo "1480"]
[TimeControl "600"]
[ECO "C20"]
[ECOUrl "https://www.chess.com/openings/Kings-Pawn-Opening"]
[Termination "Normal"]
[UTCDate "2024.01.15"]
[UTCTime "12:00:00"]

1. e4 {[%clk 0:09:58]} e5 {[%clk 0:09:57]} 2. Qh5 {[%clk 0:09:50]} Nc6 {[%clk 0:09:55]}
3. Bc4 {[%clk 0:09:40]} Nf6 {[%clk 0:09:30]} 4. Qxf7# 1-0
"""

DRAW_PGN = """[Event "Draw"]
[White "Carol"]
[Black "Dave"]
[Result "1/2-1/2"]
[TimeControl "180+2"]

1. e4 e5 2. Nf3 Nf6 3. Nxe5 d6 4. Nf3 Nxe4 5. d4 d5 6. Bd3 Be7 1/2-1/2
"""


@pytest.fixture(scope="session", autouse=True)
def _tables():
    Base.metadata.create_all(engine)
    yield


@pytest.fixture()
def session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(scope="session")
def imported_game_id():
    from app.deps import get_current_user
    from app.importer import import_pgn_text

    s = SessionLocal()
    try:
        user = get_current_user(s)
        import_pgn_text(s, user.id, SAMPLE_PGN, username="Bob", enqueue=False)
        import_pgn_text(s, user.id, DRAW_PGN, username="Carol", enqueue=False)
        s.commit()
        from sqlalchemy import select
        from app.models import Game
        g = s.scalar(
            select(Game).where(Game.white_username == "Alice", Game.black_username == "Bob")
        )
        return g.id
    finally:
        s.close()


@pytest.fixture(scope="session")
def analyzed_game_id(imported_game_id):
    """Analyse the sample game once with the real engine (skipped if absent)."""
    from app.analysis.pipeline import run_analysis
    from app.engine.manager import get_primary_config
    from app.models import Game

    s = SessionLocal()
    try:
        cfg = get_primary_config(s)
        if not cfg or not pathlib.Path(cfg.path).exists():
            pytest.skip("engine binary not available")
        cfg.depth = 10
        s.commit()
        run_analysis(s, imported_game_id, cfg=cfg, fast_depth=8, deep_depth=10)
        game = s.get(Game, imported_game_id)
        return game.id
    finally:
        s.close()
