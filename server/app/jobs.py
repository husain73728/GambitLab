"""Bounded background analysis worker (thread pool + jobs table)."""
from __future__ import annotations

import datetime as dt
import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from .config import MAX_PARALLEL_JOBS
from .db import session_scope
from .models import AnalysisJob, Game


def enqueue_game(session, game_id: int, priority: int = 50) -> AnalysisJob:
    """Idempotently queue a game for analysis."""
    existing = session.scalar(
        select(AnalysisJob).where(
            AnalysisJob.game_id == game_id,
            AnalysisJob.status.in_(["queued", "running"]),
        )
    )
    if existing is not None:
        return existing
    job = AnalysisJob(game_id=game_id, status="queued", stage="fast", priority=priority)
    session.add(job)
    game = session.get(Game, game_id)
    if game is not None and game.analysis_status in ("imported", "partial", "failed"):
        game.analysis_status = "queued"
    session.commit()
    return job


class JobWorker:
    def __init__(self, max_parallel: int = MAX_PARALLEL_JOBS):
        self.max_parallel = max_parallel
        self.executor = ThreadPoolExecutor(max_workers=max_parallel)
        self.running: set[int] = set()
        self.lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gambitlab-worker")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.executor.shutdown(wait=False)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._dispatch()
            except Exception:
                pass
            self._stop.wait(1.0)

    def _dispatch(self) -> None:
        with self.lock:
            slots = self.max_parallel - len(self.running)
        if slots <= 0:
            return
        session = session_scope()
        try:
            jobs = session.scalars(
                select(AnalysisJob)
                .where(AnalysisJob.status == "queued")
                .order_by(AnalysisJob.priority, AnalysisJob.id)
                .limit(slots)
            ).all()
            claimed = []
            for job in jobs:
                if job.id in self.running:
                    continue
                job.status = "running"
                job.started_at = dt.datetime.now(dt.timezone.utc)
                claimed.append(job.id)
            session.commit()
        finally:
            session.close()
        for job_id in claimed:
            with self.lock:
                self.running.add(job_id)
            self.executor.submit(self._run_job, job_id)

    def _run_job(self, job_id: int) -> None:
        session = session_scope()
        try:
            job = session.get(AnalysisJob, job_id)
            if job is None or job.status == "cancelled":
                return
            game = session.get(Game, job.game_id)
            if game is None:
                job.status = "failed"
                job.error = "game not found"
                session.commit()
                return
            game.analysis_status = "analyzing"
            session.commit()

            from .analysis.pipeline import run_analysis

            run_analysis(session, job.game_id, job=job)

            from .analysis.stats import invalidate_stats
            from .analysis.tactics import detect_tactics

            try:
                detect_tactics(session, job.game_id)
            except Exception:
                session.rollback()
            invalidate_stats(session, game.user_id)
        except Exception as exc:  # retry / fail gracefully
            session.rollback()
            job = session.get(AnalysisJob, job_id)
            if job is not None:
                job.attempts += 1
                game = session.get(Game, job.game_id)
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    job.error = str(exc)[:2000]
                    if game is not None:
                        game.analysis_status = "failed"
                        game.analysis_error = str(exc)[:2000]
                else:
                    job.status = "queued"  # retry
                session.commit()
        finally:
            session.close()
            with self.lock:
                self.running.discard(job_id)


worker = JobWorker()
