"""Engine registry: resolves configs and keeps one persistent process per engine."""
from __future__ import annotations

import threading
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import (
    DEFAULT_ENGINE_PATH,
    DEFAULT_HASH_MB,
    DEFAULT_THREADS,
    FAST_DEPTH,
    MULTIPV,
)
from ..models import EngineConfig
from .uci import UCIEngine


def ensure_default_config(session: Session) -> EngineConfig:
    """Create the default engine config row on first run."""
    cfg = session.scalar(select(EngineConfig).where(EngineConfig.is_default == True))  # noqa: E712
    if cfg is not None:
        return cfg
    cfg = EngineConfig(
        name="xdsa",
        kind="primary",
        path=DEFAULT_ENGINE_PATH,
        threads=DEFAULT_THREADS,
        hash_mb=DEFAULT_HASH_MB,
        depth=FAST_DEPTH,
        multipv=MULTIPV,
        is_default=True,
    )
    session.add(cfg)
    session.commit()
    return cfg


def get_primary_config(session: Session) -> EngineConfig:
    cfg = session.scalar(
        select(EngineConfig).where(EngineConfig.kind == "primary", EngineConfig.enabled == True)  # noqa: E712
    )
    return cfg or ensure_default_config(session)


def get_secondary_config(session: Session) -> Optional[EngineConfig]:
    return session.scalar(
        select(EngineConfig).where(EngineConfig.kind == "secondary", EngineConfig.enabled == True)  # noqa: E712
    )


class EngineManager:
    def __init__(self) -> None:
        self._engines: dict[tuple, UCIEngine] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _key(cfg: EngineConfig) -> tuple:
        return (cfg.path, cfg.threads, cfg.hash_mb, cfg.multipv)

    def acquire(self, cfg: EngineConfig) -> UCIEngine:
        key = self._key(cfg)
        with self._lock:
            eng = self._engines.get(key)
            if eng is None or not eng.is_alive():
                if eng is not None:
                    eng.stop()
                eng = UCIEngine(
                    path=cfg.path,
                    name=cfg.name,
                    threads=cfg.threads,
                    hash_mb=cfg.hash_mb,
                    multipv=cfg.multipv,
                    timeout=cfg.timeout_s,
                )
                eng.start()
                self._engines[key] = eng
            return eng

    def drop(self, cfg: EngineConfig) -> None:
        """Forget a (possibly crashed) engine so the next acquire restarts it."""
        with self._lock:
            eng = self._engines.pop(self._key(cfg), None)
        if eng is not None:
            eng.stop()

    def shutdown(self) -> None:
        with self._lock:
            engines = list(self._engines.values())
            self._engines.clear()
        for e in engines:
            e.stop()


manager = EngineManager()
