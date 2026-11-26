from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.ml.predictor import upsert_prediction
from app.models import Match, Prediction

router = APIRouter(prefix="/history", tags=["Riwayat & Akurasi"])


@router.get("/accuracy")
def get_accuracy_history(db: Session = Depends(get_db)):
    finished_matches = (
        db.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team), joinedload(Match.prediction))
        .filter(Match.status == "FINISHED")
        .order_by(Match.match_date.desc())
        .limit(80)
        .all()
    )

    items = []
    league_stats: dict[str, dict] = {}

    for m in finished_matches:
        pred = m.prediction or upsert_prediction(db, m)
        actual = "H" if (m.home_score or 0) > (m.away_score or 0) else ("D" if m.home_score == m.away_score else "A")
        p_h, p_d, p_a = pred.prob_home, pred.prob_draw, pred.prob_away
        predicted_1x2 = "H" if (p_h >= p_d and p_h >= p_a) else ("A" if p_a >= p_d else "D")
        correct = actual == predicted_1x2

        lg = m.league_name
        if lg not in league_stats:
            league_stats[lg] = {"league": lg, "league_code": m.league_code, "total": 0, "correct": 0}
        league_stats[lg]["total"] += 1
        if correct:
            league_stats[lg]["correct"] += 1

        items.append({
            "match_id": m.id,
            "league_code": m.league_code,
            "league_name": m.league_name,
            "date": m.match_date.isoformat(),
            "home_team": m.home_team.name,
            "away_team": m.away_team.name,
            "actual_score": f"{m.home_score} - {m.away_score}",
            "predicted_score": f"{pred.predicted_home_score} - {pred.predicted_away_score}",
            "predicted_1x2": predicted_1x2,
            "actual_1x2": actual,
            "is_correct": correct,
            "confidence": pred.confidence_score,
        })

    by_league = []
    for st in league_stats.values():
        acc = round((st["correct"] / st["total"]) * 100, 1) if st["total"] > 0 else 0.0
        by_league.append({**st, "accuracy_pct": acc})

    total_all = sum(x["total"] for x in by_league)
    correct_all = sum(x["correct"] for x in by_league)

    return {
        "overall_accuracy_pct": round((correct_all / total_all) * 100, 1) if total_all > 0 else 0.0,
        "total_evaluated": total_all,
        "by_league": by_league,
        "recent_results": items[:25],
    }
