from fastapi.testclient import TestClient

from app.main import app


def test_simulator_calculate_and_risk_levels():
    with TestClient(app) as client:
        # Valid 2 legs with manual odds
        resp = client.post(
            "/simulator/calculate",
            json={
                "title": "Tes 2 Leg",
                "legs": [
                    {"match_id": 1, "match_label": "ARS vs CHE", "market": "Home Win", "probability": 0.6, "manual_odds": 1.8},
                    {"match_id": 2, "match_label": "RMA vs BAR", "market": "Over 2.5", "probability": 0.65, "manual_odds": 1.7},
                ],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert abs(data["combined_probability"] - 0.39) < 0.001
        assert data["risk_level"] == "rendah"
        assert data["combined_odds"] == 3.06
        assert "disclaimer" in data

        # Same match correlation check
        resp_corr = client.post(
            "/simulator/calculate",
            json={
                "title": "Tes Korelasi",
                "legs": [
                    {"match_id": 1, "match_label": "ARS vs CHE", "market": "Home Win", "probability": 0.5},
                    {"match_id": 1, "match_label": "ARS vs CHE", "market": "Over 2.5", "probability": 0.5},
                ],
            },
        )
        assert resp_corr.status_code == 200
        assert resp_corr.json()["has_same_match_correlation"] is True
        assert resp_corr.json()["risk_level"] == "sedang"

        # Invalid < 2 legs
        resp_bad = client.post(
            "/simulator/calculate",
            json={
                "title": "Invalid",
                "legs": [{"match_id": 1, "match_label": "ARS vs CHE", "market": "Home Win", "probability": 0.5}],
            },
        )
        assert resp_bad.status_code == 422
