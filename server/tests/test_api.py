"""API surface via TestClient (no lifespan -> deterministic, jobs stay queued)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

EXTRA_PGN = """[Event "Extra"]
[White "Eve"]
[Black "Frank"]
[Result "0-1"]
[WhiteElo "1600"]
[BlackElo "1610"]
[TimeControl "300+3"]
[ECO "B01"]
[ECOUrl "https://www.chess.com/openings/Scandinavian-Defense"]
[UTCDate "2024.02.01"]

1. e4 d5 2. exd5 Qxd5 3. Nc3 Qa5 4. d4 Nf6 0-1
"""


def test_health_and_version():
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/version").json()["name"] == "GambitLab"


def test_me():
    r = client.get("/api/me").json()
    assert "user" in r


def test_import_and_list_games():
    r = client.post("/api/import/pgn", json={"pgn": EXTRA_PGN, "username": "Frank"})
    assert r.status_code == 200
    assert r.json()["imported"] == 1

    games = client.get("/api/games", params={"limit": 100}).json()
    assert games["total"] >= 1
    assert any(g["opponent"] in ("Eve", "Alice", "Carol") for g in games["games"])


def test_game_detail_and_filters():
    games = client.get("/api/games", params={"color": "black"}).json()["games"]
    assert games
    gid = games[0]["id"]
    detail = client.get(f"/api/games/{gid}").json()
    assert detail["game"]["id"] == gid
    assert isinstance(detail["moves"], list)

    fav = client.post(f"/api/games/{gid}/favorite", json={"value": True}).json()
    assert fav["favorite"] is True
    only_fav = client.get("/api/games", params={"favorite": True}).json()
    assert any(g["id"] == gid for g in only_fav["games"])


def test_annotations_and_notes_and_pgn_export():
    gid = client.get("/api/games").json()["games"][0]["id"]
    assert client.post(f"/api/games/{gid}/notes", json={"notes": "study this"}).json()["ok"]
    assert "id" in client.post(f"/api/games/{gid}/annotations",
                               json={"ply": 3, "comment": "key moment", "tags": ["tactic"]}).json()
    raw = client.get(f"/api/games/{gid}/pgn", params={"annotated": False}).json()["pgn"]
    assert "1." in raw or "e4" in raw


def test_analyze_enqueues_job():
    gid = client.get("/api/games", params={"status": "imported"}).json()["games"][0]["id"]
    r = client.post(f"/api/games/{gid}/analyze").json()
    assert r["job_id"] > 0
    status = client.get("/api/analysis/status").json()
    assert "games" in status


def test_dashboard_openings_breakdown_clock():
    assert "totals" in client.get("/api/dashboard").json()
    assert "openings" in client.get("/api/openings").json()
    assert "by_phase" in client.get("/api/breakdown").json()
    assert "has_data" in client.get("/api/clock").json()


def test_training_endpoints():
    assert "weaknesses" in client.get("/api/training/weaknesses").json()
    assert "recommendations" in client.get("/api/training/plan").json()
    assert "created" in client.post("/api/training/exercises/generate", json={"limit": 5}).json()
    ex = client.get("/api/training/exercises").json()
    assert "exercises" in ex


def test_assistant_is_deterministic_and_grounded():
    r = client.get("/api/assistant", params={"q": "which opening should I work on"}).json()
    assert "answer" in r
    assert isinstance(r["evidence"], list)
    # Unknown questions are explicitly marked insufficient rather than invented.
    r2 = client.get("/api/assistant", params={"q": "what is the airspeed of a swallow"}).json()
    assert r2["insufficient"] is True


def test_engine_settings_and_probe():
    s = client.get("/api/settings/engine").json()
    assert "primary" in s
    probe = client.post("/api/settings/engine/probe").json()
    assert "probe" in probe
