from fastapi.testclient import TestClient

from app.main import app
from app.ml.elo import expected_elo_score, update_elo
from app.ml.features import compute_team_context_features
from app.ml.poisson import dixon_coles_probs
from app.ml.predictor import MODEL_VERSION, calibrate_1x2_probs
from app.database import SessionLocal
from app.models import Team
from datetime import datetime, timezone


def test_dixon_coles_probabilities_sum_to_one():
    res = dixon_coles_probs(1.65, 1.15)
    total_1x2 = res.prob_home + res.prob_draw + res.prob_away
    assert abs(total_1x2 - 1.0) < 0.01
    assert abs((res.prob_over_25 + res.prob_under_25) - 1.0) < 0.01
    assert abs((res.prob_btts_yes + res.prob_btts_no) - 1.0) < 0.01
    assert res.predicted_home_score >= 0
    assert res.predicted_away_score >= 0


def test_elo_update_and_expectation():
    exp = expected_elo_score(1600, 1500)
    assert 0.5 < exp < 1.0
    new_h, new_a = update_elo(1600, 1500, 3, 0)
    assert new_h > 1600
    assert new_a < 1500


def test_predict_endpoint_with_cache():
    with TestClient(app) as client:
        matches = client.get("/matches").json()
        assert len(matches) > 0
        m_id = matches[0]["id"]

        r1 = client.get(f"/predict/{m_id}")
        assert r1.status_code == 200
        d1 = r1.json()
        assert "prob_home" in d1
        assert "prob_over_25" in d1
        assert "prob_btts_yes" in d1

        r2 = client.get(f"/predict/{m_id}")
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert r2.json()["model_version"] == MODEL_VERSION


def test_calibration_and_context_features():
    ch, cd, ca = calibrate_1x2_probs(0.75, 0.15, 0.10, temperature=1.08)
    assert abs((ch + cd + ca) - 1.0) < 0.005
    assert ch < 0.75  # temperature > 1 softens overconfident probabilities

    db = SessionLocal()
    try:
        team = db.query(Team).first()
        if team:
            ctx = compute_team_context_features(
                db,
                team,
                datetime.now(timezone.utc),
                injuries_list=[{"player": "A", "status": "Absen"}],
            )
            assert ctx["injury_penalty"] == 0.04
            assert 1.0 <= ctx["rest_days"] <= 21.0
            assert 0.0 <= ctx["weighted_form"] <= 1.0
    finally:
        db.close()
