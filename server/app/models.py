"""Normalized persistent models."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class UTCDateTime(TypeDecorator):
    """Always store naive UTC, always return timezone-aware UTC (SQLite-safe)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value.astimezone(dt.timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), default="Player")
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)

    accounts: Mapped[list["ConnectedAccount"]] = relationship(back_populates="user")
    games: Mapped[list["Game"]] = relationship(back_populates="user")


class ConnectedAccount(Base):
    """A linked Chess.com (or other) account. Public data only, no credentials."""

    __tablename__ = "connected_accounts"
    __table_args__ = (UniqueConstraint("provider", "username", name="uq_account_provider_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(40), default="chesscom")
    username: Mapped[str] = mapped_column(String(120))
    username_lower: Mapped[str] = mapped_column(String(120), index=True)
    player_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    avatar: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    joined: Mapped[Optional[dt.datetime]] = mapped_column(UTCDateTime(), nullable=True)
    raw_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_stats: Mapped[dict] = mapped_column(JSON, default=dict)
    last_synced_at: Mapped[Optional[dt.datetime]] = mapped_column(UTCDateTime(), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)

    user: Mapped[User] = relationship(back_populates="accounts")
    games: Mapped[list["Game"]] = relationship(back_populates="account")


class Game(Base):
    __tablename__ = "games"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_game_dedupe"),
        Index("ix_game_user_end", "user_id", "end_time"),
        Index("ix_game_user_status", "user_id", "analysis_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="SET NULL"), nullable=True
    )

    source: Mapped[str] = mapped_column(String(20), default="chesscom")  # chesscom | pgn
    provider_game_id: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)

    # Raw original record (kept separate from normalized/derived data).
    raw_pgn: Mapped[str] = mapped_column(Text)

    white_username: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    black_username: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    white_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    black_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    white_result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    black_result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    player_color: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)  # white|black
    player_result: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)  # win|loss|draw
    opponent_username: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    opponent_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    time_class: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # bullet|blitz|rapid|daily
    time_control: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    rules: Mapped[str] = mapped_column(String(20), default="chess")
    rated: Mapped[bool] = mapped_column(Boolean, default=True)
    eco: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    opening_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    start_time: Mapped[Optional[dt.datetime]] = mapped_column(UTCDateTime(), nullable=True)
    end_time: Mapped[Optional[dt.datetime]] = mapped_column(UTCDateTime(), nullable=True)
    termination: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    move_count: Mapped[int] = mapped_column(Integer, default=0)
    has_clock_data: Mapped[bool] = mapped_column(Boolean, default=False)

    analysis_status: Mapped[str] = mapped_column(String(20), default="imported")
    analysis_progress: Mapped[int] = mapped_column(Integer, default=0)
    analysis_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Denormalized per-game analysis summary (updated after analysis).
    acpl: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accuracy: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    best_move_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    blunders: Mapped[int] = mapped_column(Integer, default=0)
    mistakes: Mapped[int] = mapped_column(Integer, default=0)
    inaccuracies: Mapped[int] = mapped_column(Integer, default=0)
    missed_wins: Mapped[int] = mapped_column(Integer, default=0)
    missed_mates: Mapped[int] = mapped_column(Integer, default=0)
    tactical_events_count: Mapped[int] = mapped_column(Integer, default=0)
    time_pressure_errors: Mapped[int] = mapped_column(Integer, default=0)

    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )

    user: Mapped[User] = relationship(back_populates="games")
    account: Mapped[Optional[ConnectedAccount]] = relationship(back_populates="games")
    moves: Mapped[list["GameMove"]] = relationship(
        back_populates="game", cascade="all, delete-orphan", order_by="GameMove.ply"
    )
    jobs: Mapped[list["AnalysisJob"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    tactical_events: Mapped[list["TacticalEvent"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )
    annotations: Mapped[list["Annotation"]] = relationship(
        back_populates="game", cascade="all, delete-orphan"
    )


class GameMove(Base):
    __tablename__ = "game_moves"
    __table_args__ = (UniqueConstraint("game_id", "ply", name="uq_move_game_ply"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    ply: Mapped[int] = mapped_column(Integer)  # 1-based half-move
    move_number: Mapped[int] = mapped_column(Integer)
    color: Mapped[str] = mapped_column(String(6))
    san: Mapped[str] = mapped_column(String(20))
    uci: Mapped[str] = mapped_column(String(10))
    fen_before: Mapped[str] = mapped_column(String(120))
    fen_after: Mapped[str] = mapped_column(String(120))

    is_capture: Mapped[bool] = mapped_column(Boolean, default=False)
    captured_piece: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    is_check: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mate: Mapped[bool] = mapped_column(Boolean, default=False)
    clock_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    think_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Evaluations, always from WHITE's point of view. Mate stored in moves, signed.
    eval_cp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    eval_mate_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    best_uci: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    best_eval_cp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    best_mate_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Mover's-perspective derived metrics.
    cp_loss: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    classification: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    provisional: Mapped[bool] = mapped_column(Boolean, default=False)
    alternatives: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    game: Mapped[Game] = relationship(back_populates="moves")


class PositionEval(Base):
    """Cached engine evaluation keyed by position + engine + settings."""

    __tablename__ = "position_evals"
    __table_args__ = (
        UniqueConstraint("cache_key", name="uq_position_cache_key"),
        Index("ix_position_fen", "fen"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64))
    fen: Mapped[str] = mapped_column(String(120))
    engine_name: Mapped[str] = mapped_column(String(80))
    engine_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    legacy: Mapped[bool] = mapped_column(Boolean, default=False)
    depth: Mapped[int] = mapped_column(Integer)
    multipv: Mapped[list] = mapped_column(JSON, default=list)  # [{uci, cp, mate, pv}]
    best_uci: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    score_cp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # white POV
    mate_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)    # white POV
    nodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)


class EngineConfig(Base):
    __tablename__ = "engine_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(20), default="primary")  # primary | secondary
    path: Mapped[str] = mapped_column(String(400))
    threads: Mapped[int] = mapped_column(Integer, default=4)
    hash_mb: Mapped[int] = mapped_column(Integer, default=128)
    depth: Mapped[int] = mapped_column(Integer, default=14)
    multipv: Mapped[int] = mapped_column(Integer, default=3)
    nodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    timeout_s: Mapped[int] = mapped_column(Integer, default=60)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    available: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"
    __table_args__ = (Index("ix_job_status_priority", "status", "priority"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed|cancelled
    stage: Mapped[str] = mapped_column(String(20), default="fast")     # fast|deep|secondary|done
    priority: Mapped[int] = mapped_column(Integer, default=50)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    engine_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    engine_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checkpoint_ply: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)
    started_at: Mapped[Optional[dt.datetime]] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(UTCDateTime(), nullable=True)

    game: Mapped[Game] = relationship(back_populates="jobs")


class EngineEvaluation(Base):
    """Full provenance record for an analysed position."""

    __tablename__ = "engine_evaluations"
    __table_args__ = (Index("ix_eval_game_ply", "game_id", "ply"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("games.id", ondelete="CASCADE"), nullable=True
    )
    ply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fen: Mapped[str] = mapped_column(String(120), index=True)
    engine_name: Mapped[str] = mapped_column(String(80))
    engine_version: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="primary")
    depth: Mapped[int] = mapped_column(Integer)
    multipv: Mapped[int] = mapped_column(Integer, default=1)
    score_cp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mate_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    best_uci: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    pv: Mapped[list] = mapped_column(JSON, default=list)
    nodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)


class TacticalEvent(Base):
    __tablename__ = "tactical_events"
    __table_args__ = (Index("ix_tactic_user_motif", "user_id", "motif"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    ply: Mapped[int] = mapped_column(Integer)
    motif: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(10))  # found | missed
    color: Mapped[str] = mapped_column(String(6))
    fen: Mapped[str] = mapped_column(String(120))
    eval_loss_cp: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)

    game: Mapped[Game] = relationship(back_populates="tactical_events")


class TrainingExercise(Base):
    __tablename__ = "training_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    fen: Mapped[str] = mapped_column(String(120))
    side_to_move: Mapped[str] = mapped_column(String(6))
    category: Mapped[str] = mapped_column(String(40))
    motif: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    solution_uci: Mapped[str] = mapped_column(String(10))
    accepted: Mapped[list] = mapped_column(JSON, default=list)
    objective: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[int] = mapped_column(Integer, default=2)  # 1..5
    source_game_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("games.id", ondelete="SET NULL"), nullable=True
    )
    source_ply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    solves: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)
    due_at: Mapped[Optional[dt.datetime]] = mapped_column(UTCDateTime(), nullable=True)

    attempts_log: Mapped[list["TrainingAttempt"]] = relationship(
        back_populates="exercise", cascade="all, delete-orphan"
    )


class TrainingAttempt(Base):
    __tablename__ = "training_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("training_exercises.id", ondelete="CASCADE"), index=True
    )
    user_move_uci: Mapped[str] = mapped_column(String(10))
    correct: Mapped[bool] = mapped_column(Boolean, default=False)
    time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hint_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)

    exercise: Mapped[TrainingExercise] = relationship(back_populates="attempts_log")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text)
    priority: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|done|dismissed
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    week_start: Mapped[dt.datetime] = mapped_column(UTCDateTime())
    minutes_budget: Mapped[int] = mapped_column(Integer, default=120)
    items: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (UniqueConstraint("game_id", "ply", "kind", name="uq_annotation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id", ondelete="CASCADE"))
    ply: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="note")  # note|repertoire|checkpoint
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)

    game: Mapped[Game] = relationship(back_populates="annotations")


class RepertoireLine(Base):
    __tablename__ = "repertoire_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    color: Mapped[str] = mapped_column(String(6))
    moves_uci: Mapped[list] = mapped_column(JSON, default=list)
    checkpoints: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)


class StatCache(Base):
    """Materialized summaries so dashboards never recompute on every load."""

    __tablename__ = "stat_cache"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_stat_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)


class ImportLog(Base):
    __tablename__ = "import_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    account_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # chesscom|pgn
    status: Mapped[str] = mapped_column(String(20), default="running")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    games_imported: Mapped[int] = mapped_column(Integer, default=0)
    games_skipped: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(UTCDateTime(), default=utcnow)
    finished_at: Mapped[Optional[dt.datetime]] = mapped_column(UTCDateTime(), nullable=True)
