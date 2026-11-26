from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, cache, engine, get_db
from app.models import SyncLog, Team
from app.routers import history, matches, predict, simulator
from app.services.events import event_bus
from app.services.ingestion import get_sync_status, sync_league_data
from app.worker import create_scheduler

STATIC_INDEX = Path(__file__).resolve().parent / "static" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Team).count() == 0:
            sync_league_data(db, job_type="startup_seed")
    finally:
        db.close()

    scheduler = None
    if settings.ENABLE_EMBEDDED_WORKER:
        scheduler = create_scheduler()
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(
    title="Formetric API",
    description="Platform analisis statistik sepak bola & simulator kombinasi berbasis model matematis.",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(matches.router)
app.include_router(predict.router)
app.include_router(simulator.router)
app.include_router(history.router)


@app.get("/", response_class=HTMLResponse)
def web_dashboard():
    return STATIC_INDEX.read_text(encoding="utf-8")


@app.get("/health")
def health(db: Session = Depends(get_db)):
    sync_status = get_sync_status(db)
    return {
        "status": "ok",
        "service": "football-analytics-hub",
        "cache_backend": cache.backend_name,
        "cache_ok": cache.ping(),
        "sync_status": sync_status,
    }


@app.get("/sync/logs")
def get_sync_logs(db: Session = Depends(get_db)):
    rows = db.query(SyncLog).order_by(SyncLog.id.desc()).limit(20).all()
    return [
        {
            "id": r.id,
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "source": r.source,
            "job_type": r.job_type,
            "status": r.status,
            "records_upserted": r.records_upserted,
            "error_message": r.error_message,
        }
        for r in rows
    ]


@app.get("/events/stream")
async def sse_events():
    """Server-Sent Events (SSE) untuk pembaruan data otomatis ke browser tanpa refresh."""
    return StreamingResponse(
        event_bus.subscribe(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
