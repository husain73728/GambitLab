"""Application configuration for GambitLab."""
from __future__ import annotations

import os
from pathlib import Path

# Repository root = two levels up from this file (server/app/config.py -> repo).
ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("GAMBITLAB_DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite by default; set GAMBITLAB_DATABASE_URL to a PostgreSQL DSN to switch.
_default_db = f"sqlite:///{(DATA_DIR / 'gambitlab.db').as_posix()}"
DATABASE_URL = os.environ.get("GAMBITLAB_DATABASE_URL", _default_db)

# Default engine = the in-repo xdsa engine, if it has been built.
_default_engine = ROOT / "engine" / "build" / "engine.exe"
DEFAULT_ENGINE_PATH = os.environ.get("GAMBITLAB_ENGINE_PATH", str(_default_engine))

CHESSCOM_BASE = "https://api.chess.com/pub"
# Chess.com asks for a recognisable User-Agent with contact information.
USER_AGENT = os.environ.get(
    "GAMBITLAB_USER_AGENT",
    "GambitLab/0.1 (personal chess analysis; contact: local-user)",
)

# Analysis defaults (kept low so a full history does not overwhelm the machine).
FAST_DEPTH = int(os.environ.get("GAMBITLAB_FAST_DEPTH", "12"))
DEEP_DEPTH = int(os.environ.get("GAMBITLAB_DEEP_DEPTH", "18"))
DEFAULT_THREADS = int(os.environ.get("GAMBITLAB_THREADS", "4"))
DEFAULT_HASH_MB = int(os.environ.get("GAMBITLAB_HASH_MB", "128"))
MULTIPV = int(os.environ.get("GAMBITLAB_MULTIPV", "3"))

# Analysis worker.
MAX_PARALLEL_JOBS = int(os.environ.get("GAMBITLAB_MAX_PARALLEL", "2"))
POSITION_CACHE_MAX_AGE_DAYS = int(os.environ.get("GAMBITLAB_CACHE_DAYS", "30"))

# Move-classification thresholds (centipawns lost, mover's perspective).
WIN_CP_CAP = 1000          # clamp evaluations for loss math
MATE_CP = 10000            # numeric representation of a forced mate for charts/graphs
