from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Simulation

router = APIRouter(prefix="/simulator", tags=["Simulator Parlay"])


class ParlayLeg(BaseModel):
    match_id: Optional[int] = None
    match_label: str
    market: str  # e.g. "Home Win (1)", "Over 2.5", "BTTS Yes"
    probability: float = Field(..., gt=0.0, le=1.0)
    manual_odds: Optional[float] = Field(default=None, gt=1.0)


class SimulatorRequest(BaseModel):
    title: str = Field(default="Simulasi Kombinasi", max_length=150)
    legs: list[ParlayLeg] = Field(..., min_length=2, max_length=8)


def calculate_parlay_metrics(legs: list[ParlayLeg]) -> dict:
    combined_prob = 1.0
    combined_odds = 1.0
    has_all_odds = all(leg.manual_odds is not None and leg.manual_odds > 1.0 for leg in legs)

    match_ids = [leg.match_id for leg in legs if leg.match_id is not None]
    has_same_match_correlation = len(match_ids) != len(set(match_ids))

    for leg in legs:
        combined_prob *= leg.probability
        if has_all_odds and leg.manual_odds is not None:
            combined_odds *= leg.manual_odds

    combined_prob = round(combined_prob, 6)
    final_odds = round(combined_odds, 3) if has_all_odds else None
    ev = round((combined_prob * combined_odds) - 1.0, 4) if has_all_odds else None

    if combined_prob >= 0.30:
        risk_level = "rendah"
    elif combined_prob >= 0.12:
        risk_level = "sedang"
    else:
        risk_level = "tinggi"

    correlation_note = (
        "Terdeteksi beberapa pasar dari pertandingan yang sama! Asumsi independensi tidak berlaku penuh karena hasil antar-pasar saling berkorelasi."
        if has_same_match_correlation
        else "Perhitungan menggunakan asumsi independensi antar-laga: P(A ∩ B) = P(A) × P(B). Makin banyak leg, peluang gabungan turun secara eksponensial."
    )

    return {
        "leg_count": len(legs),
        "combined_probability": combined_prob,
        "combined_probability_pct": round(combined_prob * 100, 2),
        "combined_odds": final_odds,
        "expected_value": ev,
        "risk_level": risk_level,
        "has_same_match_correlation": has_same_match_correlation,
        "correlation_note": correlation_note,
        "disclaimer": "Prediksi berbasis statistik dan tidak menjamin hasil. Aplikasi ini bukan ajakan untuk berjudi. Perjudian dilarang di Indonesia.",
    }


@router.post("/calculate")
def calculate_parlay(req: SimulatorRequest):
    if not (2 <= len(req.legs) <= 8):
        raise HTTPException(status_code=400, detail="Pilih antara 2 hingga 8 pasar.")
    return calculate_parlay_metrics(req.legs)


@router.post("/save")
def save_simulation(req: SimulatorRequest, db: Session = Depends(get_db)):
    metrics = calculate_parlay_metrics(req.legs)
    sim = Simulation(
        user_id=None,
        title=req.title,
        legs_json=[leg.model_dump() for leg in req.legs],
        combined_probability=metrics["combined_probability"],
        combined_odds=metrics["combined_odds"],
        expected_value=metrics["expected_value"],
        risk_level=metrics["risk_level"],
    )
    db.add(sim)
    db.commit()
    db.refresh(sim)
    return {"id": sim.id, "title": sim.title, **metrics}


@router.get("/history")
def list_simulations(db: Session = Depends(get_db)):
    rows = db.query(Simulation).order_by(Simulation.created_at.desc()).limit(30).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "legs": r.legs_json,
            "combined_probability": r.combined_probability,
            "combined_odds": r.combined_odds,
            "expected_value": r.expected_value,
            "risk_level": r.risk_level,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
