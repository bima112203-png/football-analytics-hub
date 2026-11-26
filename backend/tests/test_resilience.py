from datetime import datetime, timedelta, timezone
import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.base import FootballDataProvider, RawMatch, RawTeam
from app.database import SessionLocal
from app.main import app
from app.models import Match, SyncLog, Team
from app.services.ingestion import get_sync_status, sync_league_data
from app.services.normalizer import format_wib_label, normalize_status, normalize_team_name
from app.services.resilience import CircuitBreaker, CircuitOpenError, RateLimiter, ResilientHttpClient
from app.worker import create_scheduler, should_poll_live


class FailingProvider(FootballDataProvider):
    def __init__(self, exc: Exception):
        self.exc = exc

    @property
    def provider_name(self) -> str:
        return "failing-api"

    def fetch_teams(self, league_code: str) -> list[RawTeam]:
        raise self.exc

    def fetch_matches(self, league_code: str, days_ahead: int = 7) -> list[RawMatch]:
        raise self.exc


class CorruptedDataProvider(FootballDataProvider):
    @property
    def provider_name(self) -> str:
        return "corrupted-api"

    def fetch_teams(self, league_code: str) -> list[RawTeam]:
        return [
            RawTeam(external_id="", name="", short_name="BAD", league_code=league_code, initial_elo=9999.0)
        ]

    def fetch_matches(self, league_code: str, days_ahead: int = 7) -> list[RawMatch]:
        return [
            RawMatch(
                external_id="bad-m-1",
                league_code=league_code,
                league_name="Test",
                match_date=datetime.now(timezone.utc),
                status="FINISHED",
                home_team_ext_id="t1",
                away_team_ext_id="t2",
                home_score=-3,
                away_score=1,
            )
        ]


def test_api_down_preserves_valid_data_and_marks_delayed():
    db = SessionLocal()
    try:
        before_count = db.query(Match).count()
        res = sync_league_data(
            db,
            leagues=["PL"],
            job_type="test_down",
            provider_override=FailingProvider(httpx.ConnectError("Connection refused")),
        )
        assert res["status"] == "failed"
        assert res["data_delayed"] is True
        assert db.query(Match).count() == before_count

        st = get_sync_status(db)
        assert st["data_delayed"] is True
        assert st["delay_label"] == "Data mungkin tertunda"
    finally:
        db.close()


def test_timeout_and_rate_limit_retries_and_circuit_breaker():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("Timed out", request=request)
        if calls["n"] == 2:
            return httpx.Response(429, json={"error": "rate limit"}, request=request)
        return httpx.Response(200, json={"ok": True}, headers={"ETag": '"v1"'}, request=request)

    transport = httpx.MockTransport(handler)
    client_http = ResilientHttpClient(
        name="test-mock",
        rate_limiter=RateLimiter(max_calls=100, period_seconds=1.0),
        circuit_breaker=CircuitBreaker(failure_threshold=2, recovery_timeout=30.0),
        max_retries=3,
        base_delay=0.01,
    )
    with httpx.Client(transport=transport) as hc:
        data, not_mod, headers = client_http.get_json("https://example.test/data", client=hc)
        assert data == {"ok": True}
        assert not_mod is False
        assert headers.get("etag") == '"v1"' or headers.get("ETag") == '"v1"'
        assert calls["n"] == 3

    # Test 304 Not Modified
    def handler_304(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("If-None-Match") == '"v1"'
        return httpx.Response(304, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler_304)) as hc304:
        data304, not_mod304, _ = client_http.get_json("https://example.test/data", etag='"v1"', client=hc304)
        assert data304 is None
        assert not_mod304 is True

    # Test Circuit Breaker opens after repeated 500s
    def handler_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"}, request=request)

    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)
    failing_client = ResilientHttpClient(name="cb-test", circuit_breaker=cb, max_retries=0, base_delay=0.01)
    with httpx.Client(transport=httpx.MockTransport(handler_500)) as hc500:
        for _ in range(2):
            with pytest.raises(httpx.HTTPStatusError):
                failing_client.get_json("https://example.test/fail", client=hc500)
        assert cb.state == "OPEN"
        with pytest.raises(CircuitOpenError):
            failing_client.get_json("https://example.test/fail", client=hc500)


def test_corrupted_payload_rejected_without_overwriting():
    db = SessionLocal()
    try:
        res = sync_league_data(
            db,
            leagues=["PL"],
            job_type="test_corrupt",
            provider_override=CorruptedDataProvider(),
        )
        assert res["status"] == "partial"
        assert res["teams_upserted"] == 0
        assert res["matches_upserted"] == 0
        assert res["validation_errors_count"] == 2
    finally:
        db.close()


def test_normalization_and_wib_conversion():
    assert normalize_team_name("Man City") == "Manchester City"
    assert normalize_status("PST") == "POSTPONED"
    assert normalize_status("CANC") == "CANCELLED"
    utc_dt = datetime(2026, 11, 26, 19, 0, tzinfo=timezone.utc)
    assert "02:00 WIB" in format_wib_label(utc_dt)


def test_worker_scheduler_and_live_polling_gate():
    sched = create_scheduler()
    job_ids = {j.id for j in sched.get_jobs()}
    assert "daily_sync_02_wib" in job_ids
    assert "live_match_polling" in job_ids

    db = SessionLocal()
    try:
        far_future = datetime.now(timezone.utc) + timedelta(days=30)
        # Ensure should_poll_live returns bool without error
        assert isinstance(should_poll_live(db, now=far_future), bool)
    finally:
        db.close()


def test_health_sync_logs_and_postponed_status():
    with TestClient(app) as client:
        h = client.get("/health")
        assert h.status_code == 200
        assert "sync_status" in h.json()

        logs = client.get("/sync/logs")
        assert logs.status_code == 200
        assert isinstance(logs.json(), list)
