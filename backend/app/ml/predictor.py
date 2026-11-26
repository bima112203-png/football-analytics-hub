import math
from typing import Optional
from sqlalchemy.orm import Session

from app.ml.elo import expected_elo_score
from app.ml.features import compute_team_context_features
from app.ml.poisson import dixon_coles_probs
from app.models import Match, Prediction

MODEL_VERSION = "dixon-coles-elo-v2-calibrated"


def calibrate_1x2_probs(p_h: float, p_d: float, p_a: float, temperature: float = 1.08) -> tuple[float, float, float]:
    """Kalibrasi probabilitas 1X2 dengan temperature scaling pada ruang log."""
    eps = 1e-6
    logits = [
        math.log(max(eps, p_h)) / temperature,
        math.log(max(eps, p_d)) / temperature,
        math.log(max(eps, p_a)) / temperature,
    ]
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    s = sum(exps)
    c_h = round(exps[0] / s, 4)
    c_d = round(exps[1] / s, 4)
    c_a = round(max(0.0, 1.0 - c_h - c_d), 4)
    return c_h, c_d, c_a


def _context_multiplier(ctx: dict) -> float:
    rest = ctx["rest_days"]
    rest_mult = 0.94 if rest < 3.0 else (1.02 if rest >= 5.0 else 1.0)
    sos_bonus = max(-0.06, min(0.08, (ctx["sos_elo"] - 1550.0) / 1500.0))
    form_mult = 0.92 + (ctx["weighted_form"] * 0.16) + sos_bonus
    injury_mult = 1.0 - ctx["injury_penalty"]
    return max(0.75, min(1.25, rest_mult * form_mult * injury_mult))


def generate_prediction_for_match(
    match: Match,
    db: Optional[Session] = None,
    elo_lookup: Optional[dict[int, float]] = None,
) -> dict:
    """Menghitung prediksi Dixon-Coles + Elo v2 (terkalibrasi) beserta fitur kontekstual."""
    home = match.home_team
    away = match.away_team
    h_stat = home.stats
    a_stat = away.stats

    h_att = h_stat.home_attack_strength if h_stat else 1.05
    h_def = h_stat.home_defense_strength if h_stat else 0.95
    a_att = a_stat.away_attack_strength if a_stat else 0.95
    a_def = a_stat.away_defense_strength if a_stat else 1.05

    h_elo = elo_lookup.get(home.id, home.elo_rating) if elo_lookup else home.elo_rating
    a_elo = elo_lookup.get(away.id, away.elo_rating) if elo_lookup else away.elo_rating

    inj_data = match.injuries_json if isinstance(match.injuries_json, dict) else {}
    h_ctx = compute_team_context_features(db, home, match.match_date, inj_data.get("home"), elo_lookup=elo_lookup)
    a_ctx = compute_team_context_features(db, away, match.match_date, inj_data.get("away"), elo_lookup=elo_lookup)

    elo_exp = expected_elo_score(h_elo, a_elo)
    elo_factor_home = 0.85 + (elo_exp * 0.45)
    elo_factor_away = 0.85 + ((1.0 - elo_exp) * 0.45)

    h_ctx_mult = _context_multiplier(h_ctx)
    a_ctx_mult = _context_multiplier(a_ctx)

    lambda_home = max(0.35, min(3.8, 1.45 * h_att * a_def * elo_factor_home * h_ctx_mult))
    lambda_away = max(0.30, min(3.5, 1.18 * a_att * h_def * elo_factor_away * a_ctx_mult))

    res = dixon_coles_probs(lambda_home, lambda_away)
    cal_h, cal_d, cal_a = calibrate_1x2_probs(res.prob_home, res.prob_draw, res.prob_away)

    max_p = max(cal_h, cal_d, cal_a)
    confidence = round(min(95.0, max(35.0, max_p * 112.0)), 1)

    if cal_h >= cal_a and cal_h >= cal_d:
        fav = f"{home.name} lebih diunggulkan menang ({cal_h * 100:.1f}%)"
    elif cal_a >= cal_h and cal_a >= cal_d:
        fav = f"{away.name} lebih diunggulkan menang ({cal_a * 100:.1f}%)"
    else:
        fav = f"Laga berpeluang ketat menuju hasil seri ({cal_d * 100:.1f}%)"

    explanation = (
        f"{fav}. Rating Elo: {home.short_name} ({h_elo:.0f}) vs {away.short_name} ({a_elo:.0f}). "
        f"Form berbobot: {h_ctx['weighted_form']:.2f} vs {a_ctx['weighted_form']:.2f}; "
        f"istirahat: {h_ctx['rest_days']:.0f}h vs {a_ctx['rest_days']:.0f}h; "
        f"kekuatan jadwal (SoS Elo): {h_ctx['sos_elo']:.0f} vs {a_ctx['sos_elo']:.0f}. "
        f"Ekspektasi gol model: {lambda_home:.2f} - {lambda_away:.2f}."
    )

    return {
        "match_id": match.id,
        "model_version": MODEL_VERSION,
        "prob_home": cal_h,
        "prob_draw": cal_d,
        "prob_away": cal_a,
        "prob_over_25": res.prob_over_25,
        "prob_under_25": res.prob_under_25,
        "prob_btts_yes": res.prob_btts_yes,
        "prob_btts_no": res.prob_btts_no,
        "expected_home_goals": round(lambda_home, 3),
        "expected_away_goals": round(lambda_away, 3),
        "predicted_home_score": res.predicted_home_score,
        "predicted_away_score": res.predicted_away_score,
        "confidence_score": confidence,
        "explanation_text": explanation,
        "context_features": {"home": h_ctx, "away": a_ctx},
    }


def upsert_prediction(db: Session, match: Match) -> Prediction:
    """Menyimpan atau memperbarui hasil prediksi ke tabel predictions."""
    pred_dict = generate_prediction_for_match(match, db=db)
    pred_dict.pop("context_features", None)
    pred = db.query(Prediction).filter(Prediction.match_id == match.id).first()

    is_correct = None
    if match.status == "FINISHED" and match.home_score is not None and match.away_score is not None:
        actual = "H" if match.home_score > match.away_score else ("D" if match.home_score == match.away_score else "A")
        p_h, p_d, p_a = pred_dict["prob_home"], pred_dict["prob_draw"], pred_dict["prob_away"]
        predicted = "H" if (p_h >= p_d and p_h >= p_a) else ("A" if p_a >= p_d else "D")
        is_correct = actual == predicted

    if not pred:
        pred = Prediction(**pred_dict, is_correct_1x2=is_correct)
        db.add(pred)
    else:
        for k, v in pred_dict.items():
            setattr(pred, k, v)
        pred.is_correct_1x2 = is_correct

    db.commit()
    db.refresh(pred)
    return pred
