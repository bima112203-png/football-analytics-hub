import json
import time
from typing import Any, Optional

import redis
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency generator untuk sesi database SQLAlchemy."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class CacheClient:
    """Wrapper Redis dengan fallback otomatis ke in-memory cache untuk development lokal."""

    def __init__(self, redis_url: str):
        self._memory: dict[str, tuple[float, str]] = {}
        self._redis: Optional[redis.Redis] = None
        try:
            client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1)
            client.ping()
            self._redis = client
        except Exception:
            self._redis = None

    @property
    def backend_name(self) -> str:
        return "redis" if self._redis is not None else "memory-fallback"

    def ping(self) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.ping())
            except Exception:
                return False
        return True

    def get_json(self, key: str) -> Optional[Any]:
        if self._redis is not None:
            try:
                val = self._redis.get(key)
                return json.loads(val) if val is not None else None
            except Exception:
                pass
        entry = self._memory.get(key)
        if not entry:
            return None
        expires_at, raw = entry
        if time.time() > expires_at:
            self._memory.pop(key, None)
            return None
        return json.loads(raw)

    def set_json(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        raw = json.dumps(value, default=str)
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl_seconds, raw)
                return
            except Exception:
                pass
        self._memory[key] = (time.time() + ttl_seconds, raw)

    def delete_prefix(self, prefix: str) -> None:
        if self._redis is not None:
            try:
                for k in self._redis.scan_iter(f"{prefix}*"):
                    self._redis.delete(k)
                return
            except Exception:
                pass
        for k in list(self._memory.keys()):
            if k.startswith(prefix):
                self._memory.pop(k, None)


cache = CacheClient(settings.REDIS_URL)
