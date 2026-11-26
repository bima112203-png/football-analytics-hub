from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import cache, get_db
from app.ml.predictor import upsert_prediction
from app.models import Match, Team
from app.schemas import PredictionSummaryOut

router = APIRouter(tags=["Prediksi"])


@router.get("/predict/{match_id}")
def predict_match(match_id: int, db: Session = Depends(get_db)):
    cache_key = f"predict:{match_id}"
    cached = cache.get_json(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    match = (
        db.query(Match)
        .options(
            joinedload(Match.home_team).joinedload(Team.stats),
            joinedload(Match.away_team).joinedload(Team.stats),
        )
        .filter(Match.id == match_id)
        .first()
    )
    if not match:
        raise HTTPException(status_code=404, detail="Pertandingan tidak ditemukan.")

    pred = upsert_prediction(db, match)
    payload = PredictionSummaryOut.model_validate(pred).model_dump(mode="json")
    payload["match_id"] = match.id
    payload["home_team"] = match.home_team.name
    payload["away_team"] = match.away_team.name
    payload["model_version"] = pred.model_version

    cache.set_json(cache_key, payload, ttl_seconds=900)
    return {**payload, "cached": False}
