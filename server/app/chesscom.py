"""Chess.com public-data API client.

Uses only documented PubAPI endpoints, sends a recognisable User-Agent, makes
strictly serial requests, honours ETag caching and backs off on 429/5xx. No
credentials are ever requested or stored.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

import httpx

from .config import CHESSCOM_BASE, DATA_DIR, USER_AGENT

CACHE_DIR = DATA_DIR / "httpcache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class ChessComError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def _cache_path(url: str) -> Path:
    h = hashlib.sha256(url.encode()).hexdigest()[:24]
    return CACHE_DIR / f"{h}.json"


def _load_cache(url: str) -> Optional[dict]:
    p = _cache_path(url)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(url: str, etag: Optional[str], data: Any) -> None:
    p = _cache_path(url)
    p.write_text(json.dumps({"etag": etag, "data": data}), encoding="utf-8")


class ChessComClient:
    def __init__(self, timeout: float = 20.0, max_retries: int = 3):
        self._client = httpx.Client(
            base_url=CHESSCOM_BASE,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=timeout,
            follow_redirects=True,
        )
        self.max_retries = max_retries

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ChessComClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get(self, path: str) -> Any:
        url = f"{CHESSCOM_BASE}{path}"
        cached = _load_cache(url)
        headers = {}
        if cached and cached.get("etag"):
            headers["If-None-Match"] = cached["etag"]

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = self._client.get(path, headers=headers)
            except httpx.HTTPError as exc:  # network layer
                last_err = exc
                time.sleep(0.5 * (attempt + 1))
                continue

            if resp.status_code == 304 and cached:
                return cached["data"]
            if resp.status_code == 200:
                data = resp.json()
                _save_cache(url, resp.headers.get("ETag"), data)
                return data
            if resp.status_code == 404:
                raise ChessComError("Not found", 404)
            if resp.status_code in (429, 500, 502, 503, 504):
                last_err = ChessComError(f"HTTP {resp.status_code}", resp.status_code)
                time.sleep(1.5 * (attempt + 1))  # back off
                continue
            raise ChessComError(f"HTTP {resp.status_code}", resp.status_code)

        raise ChessComError(f"Request failed: {last_err}")

    # -- Endpoints ---------------------------------------------------------
    def profile(self, username: str) -> dict:
        return self._get(f"/player/{username}")

    def stats(self, username: str) -> dict:
        return self._get(f"/player/{username}/stats")

    def archives(self, username: str) -> list[str]:
        return self._get(f"/player/{username}/games/archives").get("archives", [])

    def monthly_games(self, year: int, month: int, archive_url: Optional[str] = None,
                      username: Optional[str] = None) -> list[dict]:
        if archive_url:
            # archive_url is absolute; strip the base to reuse the client.
            path = archive_url.replace(CHESSCOM_BASE, "")
        else:
            path = f"/player/{username}/games/{year}/{month:02d}"
        return self._get(path).get("games", [])

    def archive_pgn(self, username: str, year: int, month: int) -> str:
        """Multi-game PGN for a month (optional fast path)."""
        resp = self._client.get(
            f"/player/{username}/games/{year}/{month:02d}/pgn",
            headers={"Accept": "application/x-chess-pgn"},
        )
        resp.raise_for_status()
        return resp.text
