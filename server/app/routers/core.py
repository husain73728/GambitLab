"""Onboarding, import, dashboard, progress, settings and assistant routes."""
from __future__ import annotations

import threading
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analysis.stats import dashboard as dashboard_stats
from ..analysis.stats import progress as progress_stats
from ..chesscom import ChessComClient, ChessComError
from ..config import DEEP_DEPTH, FAST_DEPTH, DEFAULT_ENGINE_PATH
from ..db import get_session, session_scope
from ..deps import get_account, get_current_user
from ..engine.manager import ensure_default_config, get_primary_config
from ..engine.uci import probe_engine
from ..importer import import_chesscom_account, import_pgn_text
from ..models import ConnectedAccount, EngineConfig, ImportLog, User

router = APIRouter(prefix="/api", tags=["core"])


class OnboardRequest(BaseModel):
    username: str


class ImportRequest(BaseModel):
    username: Optional[str] = None
    months: Optional[int] = None
    time_classes: Optional[list[str]] = None
    all_history: bool = False


class PgnImport(BaseModel):
    pgn: str
    username: Optional[str] = None


class EngineUpdate(BaseModel):
    path: Optional[str] = None
    threads: Optional[int] = None
    hash_mb: Optional[int] = None
    depth: Optional[int] = None
    timeout_s: Optional[int] = None
    multipv: Optional[int] = None
    name: Optional[str] = None


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/me")
def me(session: Session = Depends(get_session)):
    user = get_current_user(session)
    acct = get_account(session, user.id)
    return {
        "user": {"id": user.id, "display_name": user.display_name},
        "account": _account_dict(acct) if acct else None,
    }


def _account_dict(a: ConnectedAccount) -> dict:
    return {
        "id": a.id, "provider": a.provider, "username": a.username,
        "name": a.name, "avatar": a.avatar, "title": a.title, "status": a.status,
        "player_id": a.player_id,
        "last_synced_at": a.last_synced_at.isoformat() if a.last_synced_at else None,
        "stats": a.raw_stats,
    }


@router.get("/onboard/preview")
def preview(username: str):
    try:
        with ChessComClient() as client:
            profile = client.profile(username)
            stats = client.stats(username)
    except ChessComError as exc:
        raise HTTPException(status_code=404 if exc.status == 404 else 502,
                            detail=f"Chess.com lookup failed: {exc}")
    return {
        "username": profile.get("username"),
        "name": profile.get("name"),
        "avatar": profile.get("avatar"),
        "title": profile.get("title"),
        "status": profile.get("status"),
        "country": profile.get("country"),
        "joined": profile.get("joined"),
        "player_id": profile.get("player_id"),
        "stats": stats,
    }


@router.post("/onboard")
def onboard(req: OnboardRequest, session: Session = Depends(get_session)):
    user = get_current_user(session)
    try:
        with ChessComClient() as client:
            profile = client.profile(req.username)
            stats = client.stats(req.username)
    except ChessComError as exc:
        raise HTTPException(status_code=404 if exc.status == 404 else 502,
                            detail=f"Chess.com lookup failed: {exc}")

    acct = get_account(session, user.id)
    if acct is None:
        acct = ConnectedAccount(user_id=user.id, provider="chesscom", username=req.username,
                                username_lower=req.username.lower())
        session.add(acct)
    acct.username = profile.get("username", req.username)
    acct.username_lower = acct.username.lower()
    acct.player_id = profile.get("player_id")
    acct.name = profile.get("name")
    acct.avatar = profile.get("avatar")
    acct.country = profile.get("country")
    acct.title = profile.get("title")
    acct.status = profile.get("status")
    acct.raw_profile = profile
    acct.raw_stats = stats
    session.commit()
    ensure_default_config(session)
    return {"account": _account_dict(acct)}


@router.post("/import/chesscom")
def import_chesscom(req: ImportRequest, session: Session = Depends(get_session)):
    user = get_current_user(session)
    acct = get_account(session, user.id)
    if acct is None:
        raise HTTPException(status_code=400, detail="Link a Chess.com account first")
    if req.username and req.username.lower() != acct.username_lower:
        raise HTTPException(status_code=400, detail="Username does not match the linked account")

    months = None if req.all_history else (req.months or 3)

    def _run():
        s = session_scope()
        try:
            a = s.get(ConnectedAccount, acct.id)
            import_chesscom_account(s, a, limit_months=months, time_classes=req.time_classes)
        except Exception:
            s.rollback()
        finally:
            s.close()

    threading.Thread(target=_run, daemon=True).start()
    return {"status": "started", "months": months or "all"}


@router.post("/import/pgn")
def import_pgn(req: PgnImport, session: Session = Depends(get_session)):
    user = get_current_user(session)
    acct = get_account(session, user.id)
    imported, skipped = import_pgn_text(
        session, user.id, req.pgn,
        account_id=acct.id if acct else None,
        username=req.username or (acct.username if acct else None),
    )
    session.add(ImportLog(user_id=user.id, kind="pgn", status="done",
                          games_imported=imported, games_skipped=skipped))
    session.commit()
    return {"imported": imported, "skipped": skipped}


@router.get("/import/logs")
def import_logs(session: Session = Depends(get_session), limit: int = 20):
    user = get_current_user(session)
    logs = session.scalars(
        select(ImportLog).where(ImportLog.user_id == user.id).order_by(ImportLog.id.desc()).limit(limit)
    ).all()
    return {"logs": [
        {"id": l.id, "kind": l.kind, "status": l.status, "imported": l.games_imported,
         "skipped": l.games_skipped, "error": l.error,
         "created_at": l.created_at.isoformat() if l.created_at else None,
         "finished_at": l.finished_at.isoformat() if l.finished_at else None}
        for l in logs
    ]}


@router.get("/dashboard")
def dashboard(days: Optional[int] = None, session: Session = Depends(get_session)):
    user = get_current_user(session)
    return dashboard_stats(session, user.id, days)


@router.get("/progress")
def progress(window: int = 50, session: Session = Depends(get_session)):
    user = get_current_user(session)
    return progress_stats(session, user.id, window)


@router.get("/settings/engine")
def get_engine_settings(session: Session = Depends(get_session)):
    get_current_user(session)
    cfg = get_primary_config(session)
    return {"primary": _engine_dict(cfg), "defaults": {
        "path": DEFAULT_ENGINE_PATH, "fast_depth": FAST_DEPTH, "deep_depth": DEEP_DEPTH,
    }}


def _engine_dict(cfg: EngineConfig) -> dict:
    return {
        "id": cfg.id, "name": cfg.name, "kind": cfg.kind, "path": cfg.path,
        "threads": cfg.threads, "hash_mb": cfg.hash_mb, "depth": cfg.depth,
        "multipv": cfg.multipv, "timeout_s": cfg.timeout_s,
        "available": cfg.available, "version": cfg.version,
    }


@router.post("/settings/engine")
def update_engine_settings(req: EngineUpdate, session: Session = Depends(get_session)):
    get_current_user(session)
    cfg = get_primary_config(session)
    for field in ("path", "threads", "hash_mb", "depth", "timeout_s", "multipv", "name"):
        val = getattr(req, field)
        if val is not None:
            setattr(cfg, field, val)
    cfg.available = None
    session.commit()
    return {"primary": _engine_dict(cfg)}


@router.post("/settings/engine/probe")
def probe_settings(session: Session = Depends(get_session)):
    get_current_user(session)
    cfg = get_primary_config(session)
    info = probe_engine(cfg.path)
    cfg.available = info["available"]
    cfg.version = info.get("version")
    session.commit()
    return {"probe": info, "primary": _engine_dict(cfg)}
