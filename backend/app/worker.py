"""Worker terpisah untuk sinkronisasi harian (02:00 WIB) dan polling live pertandingan."""
from datetime import datetime, timedelta, timezone
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.logging_config import get_logger
from app.models import Match
from app.services.ingestion import sync_league_data

logger = get_logger("worker")


def should_poll_live(db: Session, now: datetime | None = None) -> bool:
    """Mengembalikan True hanya jika ada laga LIVE atau sedang berada di jendela kickoff."""
    ref = now or datetime.now(timezone.utc)
    live_count = db.query(Match).filter(Match.status == "LIVE").count()
    if live_count > 0:
        return True

    window_start = ref - timedelta(minutes=120)
    window_end = ref + timedelta(minutes=15)
    imminent = (
        db.query(Match)
        .filter(
            Match.status == "SCHEDULED",
            Match.match_date >= window_start,
            Match.match_date <= window_end,
        )
        .count()
    )
    return imminent > 0


def run_daily_sync() -> dict:
    db = SessionLocal()
    try:
        logger.info("Menjalankan job sinkronisasi harian 02:00 WIB")
        return sync_league_data(db, job_type="daily", recalculate_predictions=True)
    finally:
        db.close()


def run_live_poll() -> dict:
    db = SessionLocal()
    try:
        if not should_poll_live(db):
            return {"status": "skipped", "reason": "tidak ada pertandingan berlangsung"}
        logger.info("Menjalankan job polling live (ada laga berlangsung)")
        return sync_league_data(db, days_ahead=1, job_type="live_poll", recalculate_predictions=True)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
    # 1. Sinkronisasi harian pukul 02:00 WIB
    scheduler.add_job(
        run_daily_sync,
        trigger=CronTrigger(hour=2, minute=0, timezone="Asia/Jakarta"),
        id="daily_sync_02_wib",
        replace_existing=True,
    )
    # 2. Polling live setiap 45 detik (hanya aktif memanggil API bila ada laga berlangsung)
    scheduler.add_job(
        run_live_poll,
        trigger=IntervalTrigger(seconds=45),
        id="live_match_polling",
        replace_existing=True,
    )
    return scheduler


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    sched = create_scheduler()
    sched.start()
    logger.info("Worker APScheduler aktif (Harian 02:00 WIB & Live Polling 45 detik)")
    try:
        while True:
            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        sched.shutdown()
        logger.info("Worker APScheduler dihentikan.")
