"""Manual end-to-end smoke check: import a PGN, analyse it, print stats.

Run from server/:  python scripts/smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.pipeline import run_analysis  # noqa: E402
from app.analysis.stats import dashboard, move_breakdown  # noqa: E402
from app.analysis.training import generate_puzzles, build_plan, weakness_report  # noqa: E402
from app.db import engine as db_engine, session_scope  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.engine.manager import ensure_default_config  # noqa: E402
from app.importer import import_pgn_text  # noqa: E402
from app.models import Base, Game  # noqa: E402
from sqlalchemy import select  # noqa: E402

PGN = """[Event "GambitLab smoke"]
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


def main() -> int:
    Base.metadata.create_all(db_engine)
    session = session_scope()
    try:
        user = get_current_user(session)
        cfg = ensure_default_config(session)
        cfg.depth = 10
        session.commit()

        imported, skipped = import_pgn_text(session, user.id, PGN, username="Bob", enqueue=False)
        print(f"imported={imported} skipped={skipped}")

        game = session.scalar(select(Game).order_by(Game.id.desc()))
        assert game is not None
        print(f"game {game.id}: {game.white_username} vs {game.black_username} "
              f"player={game.player_color} result={game.player_result} opening={game.opening_name}")

        result = run_analysis(session, game.id, cfg=cfg, fast_depth=8, deep_depth=10)
        print("analysis:", result)

        session.refresh(game)
        print(f"acpl={game.acpl} blunders={game.blunders} mistakes={game.mistakes} "
              f"missed_wins={game.missed_wins} missed_mates={game.missed_mates} "
              f"tp_errors={game.time_pressure_errors} status={game.analysis_status}")

        for m in game.moves:
            print(f"  {m.ply:>2} {m.san:<7} {str(m.classification):<11} loss={m.cp_loss} "
                  f"eval={m.eval_cp} best={m.best_uci}")

        dash = dashboard(session, user.id)
        print("dashboard totals:", dash["totals"])
        print("analysis:", dash["analysis"])
        print("performance:", dash["performance"])

        print("breakdown:", move_breakdown(session, user.id)["by_phase"])
        print("weaknesses:", [w["label"] for w in weakness_report(session, user.id)][:5])
        print("puzzles created:", generate_puzzles(session, user.id, 10))
        plan = build_plan(session, user.id, 90)
        print("plan:", plan.summary)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
