from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.database import Base, engine
from app.main import app
from scripts.seed import run_seed


def test_database_schema_and_seed():
    run_seed()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    expected = {"users", "teams", "matches", "team_stats", "predictions", "simulations"}
    assert expected.issubset(tables)


def test_health_and_matches_endpoints():
    run_seed()
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        matches_resp = client.get("/matches")
        assert matches_resp.status_code == 200
        data = matches_resp.json()
        assert len(data) > 0

        pl_resp = client.get("/matches?league=PL")
        assert pl_resp.status_code == 200
        pl_data = pl_resp.json()
        assert len(pl_data) > 0
        assert all(m["league_code"] == "PL" for m in pl_data)

        first_id = pl_data[0]["id"]
        detail_resp = client.get(f"/matches/{first_id}")
        assert detail_resp.status_code == 200
        detail = detail_resp.json()
        assert detail["id"] == first_id
        assert "head_to_head" in detail
        assert "home_recent_matches" in detail
        assert "away_recent_matches" in detail

        standings = client.get("/standings?league=PL")
        assert standings.status_code == 200
        s_rows = standings.json()
        assert len(s_rows) > 0
        assert s_rows[0]["position"] == 1
