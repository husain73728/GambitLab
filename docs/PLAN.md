# GambitLab — implementation plan

A personal chess analytics and improvement platform. Single-user, local-first.

## Stack (chosen for this hardware/repo)

- **Backend:** Python 3.10 + FastAPI, SQLAlchemy 2.0, SQLite (file DB; `DATABASE_URL`
  can point at PostgreSQL). Uvicorn server.
- **Chess:** `python-chess` for legality, PGN parsing, clocks, openings.
- **Engine:** generic UCI process manager. Default engine = the in-repo `xdsa`
  (`engine/build/engine.exe`); Stockfish / Lc0 pluggable via settings.
- **Jobs:** in-process bounded worker (thread) driven by an `analysis_jobs` table
  (no Redis needed for a single-user local app).
- **Frontend:** React + TypeScript + Vite, Tailwind CSS, Recharts,
  `react-chessboard`, `chess.js`.
- **Tests:** pytest (backend).

## Data flow

Chess.com public API (or manual PGN) → normalize + dedupe → `games`/`game_moves`
→ enqueue `analysis_jobs` → worker drives the UCI engine → `engine_evaluations` +
per-move `cp_loss`/classification → `tactical_events` → aggregate stats/caches →
dashboard, library, board, openings, clock, training.

## Milestones

1. Frontend shell with navigation + analysis workspace (done alongside 2-5).
2. Chess.com integration + manual PGN import.
3. Persistent normalized storage.
4. Real engine integration + move-by-move analysis (staged: fast scan → deep).
5. Statistics, openings, clock, weakness detection.
6. Optional secondary engine.
7. Puzzle generation + training plans.
8. Trend analytics + explainable recommendations + final tests.

## Provenance rules

- Chess.com data and engine analysis are stored separately.
- Every evaluation records engine name/version/depth/nodes/multipv.
- Numerical claims come from deterministic SQL/Python, never a language model.
