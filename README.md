# GambitLab

A personal chess analytics and improvement platform — a local-first "chess coach"
backed by a chess engine and your own game data.

It ingests games from Chess.com's public API (or manual PGN), stores them in a
normalized database, analyses every position with a UCI engine, and turns the
results into statistics, weakness reports and personal training exercises.

> Original name and interface. Not affiliated with Chess.com; no protected
> Chess.com assets are used.

## Repository layout

```
engine/     C++ UCI chess engine ("xdsa") — bitboards, search, evaluation
server/     Python FastAPI backend + analysis pipeline + tests
web/        React + TypeScript frontend (the GambitLab interface)
trainer/    Python venv (torch/numpy) used for ML work
data/       SQLite database + HTTP cache (generated)
docs/       implementation plan
run.ps1     start the backend (serves API + built frontend)
build.ps1   build the C++ engine
```

## What it does

- **Onboarding** — look up a Chess.com username, preview profile + stats, import
  a time range or full history, filter by time control, or paste PGN by hand.
- **Dashboard** — rating progression per time control, win rates, activity by
  day/hour/weekday, results by colour and opponent rating, mistake profile,
  analysis status, and a deterministic question box.
- **Game library** — filter by date, result, colour, opponent rating, opening,
  blunders, analysis status, missed wins and time-pressure errors.
- **Analysis workspace** — interactive board, move list with quality
  annotations, evaluation bar and graph, engine lines, best-move arrows,
  clock/thinking time, tactics, notes, PGN export with annotations.
- **Openings, Tactics, Clock, Progress** — openings explorer + repertoire,
  recurring tactical motifs, time-management analytics, before/after trends.
- **Training** — weakness detection with a transparent priority formula, a
  weekly plan, and puzzles generated from your own mistakes with spaced review.

## Requirements

- Windows with the MSYS2 UCRT64 toolchain (for the C++ engine) — optional, a
  Stockfish binary can be used instead.
- Python 3.10 (`trainer\.venv`) — already created in this repo.
- Node.js 20+ (for building the frontend).

## Setup

```powershell
# 1. Backend dependencies
trainer\.venv\Scripts\python.exe -m pip install -r server\requirements.txt

# 2. Build the C++ engine (optional; Stockfish also works)
./build.ps1

# 3. Build the frontend
cd web
npm install
npm run build      # outputs web/dist, served by the backend
cd ..
```

## Run

```powershell
./run.ps1
# open http://127.0.0.1:8000
```

For frontend development with hot reload:

```powershell
# terminal 1
./run.ps1 -Reload
# terminal 2
cd web; npm run dev     # http://127.0.0.1:5173 (proxies /api to :8000)
```

## Tests

```powershell
cd server
..\trainer\.venv\Scripts\python.exe -m pytest -q
```

## Engine

The default analyser is the in-repo `xdsa` engine (`engine/build/engine.exe`).
Point it at Stockfish in **Settings** for stronger, faster analysis — the engine
layer is a generic UCI process manager. Every stored evaluation records engine
name, version, depth, MultiPV and settings so results are reproducible.

## Data & provenance

- Chess.com data is fetched only through the documented public API with a
  custom User-Agent, ETag caching and serial (rate-limit friendly) requests.
  No credentials are ever requested or stored.
- Raw PGNs are stored separately from normalized records.
- Numerical claims (statistics, priorities, centipawn loss) are computed
  deterministically in SQL/Python; no language model invents values.
- A language-model-free assistant answers questions by querying stored games
  and analysis, and says "insufficient evidence" when data is thin.
