import asyncio
import json
from typing import AsyncGenerator


class EventBus:
    """Broadcast event ringan untuk Server-Sent Events (SSE)."""

    def __init__(self):
        self._subscribers: set[asyncio.Queue[str]] = set()

    def publish(self, event_type: str, data: dict) -> None:
        payload = json.dumps({"type": event_type, "data": data}, default=str)
        for q in list(self._subscribers):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncGenerator[str, None]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=50)
        self._subscribers.add(q)
        try:
            yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=25.0)
                    yield f"event: update\ndata: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            self._subscribers.discard(q)


event_bus = EventBus()
