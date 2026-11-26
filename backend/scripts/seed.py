"""Skrip seeding database awal untuk Football Analytics Hub."""
from app.database import Base, SessionLocal, engine
from app.services.ingestion import sync_league_data


def run_seed() -> dict:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        result = sync_league_data(db)
        print(f"[SEED] Selesai: {result}")
        return result
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
