import random
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, field_validator

from app.logging_config import get_logger

logger = get_logger("resilience")


class CircuitOpenError(RuntimeError):
    """Dilempar ketika circuit breaker dalam kondisi OPEN akibat kegagalan berulang."""


class RateLimiter:
    """Token-bucket rate limiter sederhana yang aman untuk multi-thread."""

    def __init__(self, max_calls: int = 10, period_seconds: float = 60.0):
        self.max_calls = max(1, max_calls)
        self.period_seconds = max(0.1, period_seconds)
        self._tokens = float(self.max_calls)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            refill = elapsed * (self.max_calls / self.period_seconds)
            self._tokens = min(float(self.max_calls), self._tokens + refill)
            self._last_refill = now
            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) * (self.period_seconds / self.max_calls)
                time.sleep(min(wait_time, 2.0))
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


class CircuitBreaker:
    """Circuit breaker untuk mencegah pemanggilan berulang saat API eksternal down."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED | OPEN | HALF_OPEN
        self.opened_at: Optional[float] = None
        self._lock = threading.Lock()

    def allow_request(self) -> bool:
        with self._lock:
            if self.state == "CLOSED":
                return True
            if self.state == "OPEN":
                if self.opened_at and (time.monotonic() - self.opened_at) >= self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    return True
                return False
            return True  # HALF_OPEN

    def record_success(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                self.opened_at = time.monotonic()

    def reset(self) -> None:
        with self._lock:
            self.failure_count = 0
            self.state = "CLOSED"
            self.opened_at = None


class ResilientHttpClient:
    """HTTP Client dengan rate limiter, ETag/If-Modified-Since, exponential backoff + jitter, dan circuit breaker."""

    def __init__(
        self,
        name: str,
        rate_limiter: Optional[RateLimiter] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        max_retries: int = 3,
        base_delay: float = 0.4,
        timeout: float = 10.0,
    ):
        self.name = name
        self.rate_limiter = rate_limiter or RateLimiter(max_calls=20, period_seconds=60.0)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.timeout = timeout

    def get_json(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, Any]] = None,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ) -> tuple[Optional[Any], bool, dict[str, str]]:
        """
        Mengembalikan (json_data, not_modified, response_headers).
        Melempar exception bila semua retry gagal atau circuit breaker terbuka.
        """
        if not self.circuit_breaker.allow_request():
            raise CircuitOpenError(f"Circuit breaker {self.name} sedang OPEN.")

        req_headers = dict(headers or {})
        if etag:
            req_headers["If-None-Match"] = etag
        if last_modified:
            req_headers["If-Modified-Since"] = last_modified

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self.rate_limiter.acquire()
            try:
                if client is not None:
                    resp = client.get(url, headers=req_headers, params=params, timeout=self.timeout)
                else:
                    with httpx.Client(timeout=self.timeout) as local_client:
                        resp = local_client.get(url, headers=req_headers, params=params)

                if resp.status_code == 304:
                    self.circuit_breaker.record_success()
                    return None, True, dict(resp.headers)

                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code} dari {self.name}",
                        request=resp.request,
                        response=resp,
                    )

                resp.raise_for_status()
                data = resp.json()
                self.circuit_breaker.record_success()
                return data, False, dict(resp.headers)

            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError, ValueError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt) + random.uniform(0.05, 0.25)
                    logger.warning(
                        f"Retry {attempt + 1}/{self.max_retries} untuk {self.name}",
                        extra={"extra_data": {"url": url, "error": str(exc), "delay_s": round(delay, 3)}},
                    )
                    time.sleep(delay)
                else:
                    self.circuit_breaker.record_failure()

        assert last_exc is not None
        raise last_exc


class ValidatedRawTeam(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=150)
    short_name: str = Field(..., min_length=1, max_length=30)
    league_code: str = Field(..., min_length=1, max_length=20)
    crest_url: Optional[str] = None
    initial_elo: float = Field(default=1500.0, ge=500.0, le=2800.0)


class ValidatedRawMatch(BaseModel):
    external_id: str = Field(..., min_length=1, max_length=80)
    league_code: str = Field(..., min_length=1, max_length=20)
    league_name: str = Field(..., min_length=1, max_length=120)
    match_date: datetime
    status: str
    home_team_ext_id: str = Field(..., min_length=1, max_length=80)
    away_team_ext_id: str = Field(..., min_length=1, max_length=80)
    home_score: Optional[int] = Field(default=None, ge=0, le=50)
    away_score: Optional[int] = Field(default=None, ge=0, le=50)

    @field_validator("match_date", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        if isinstance(v, str):
            v = datetime.fromisoformat(v.replace("Z", "+00:00"))
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v.astimezone(timezone.utc)
        raise ValueError("Format match_date tidak valid")
