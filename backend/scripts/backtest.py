"""Skrip backtesting kronologis (walk-forward) bebas data leakage untuk model Dixon-Coles + Elo v2."""
import math
from sqlalchemy.orm import joinedload

from app.database import SessionLocal
from app.ml.elo import update_elo
from app.ml.predictor import MODEL_VERSION, generate_prediction_for_match
from app.models import Match, Team


def run_backtest(initial_elo: float = 1550.0) -> dict:
    db = SessionLocal()
    try:
        matches = (
            db.query(Match)
            .options(
                joinedload(Match.home_team).joinedload(Team.stats),
                joinedload(Match.away_team).joinedload(Team.stats),
            )
            .filter(Match.status == "FINISHED", Match.home_score.isnot(None), Match.away_score.isnot(None))
            .order_by(Match.match_date.asc())
            .all()
        )
        if not matches:
            print("[BACKTEST] Tidak ada pertandingan selesai untuk dievaluasi.")
            return {"total_matches": 0}

        # Mulai walk-forward dari baseline netral agar bebas kebocoran data masa depan
        elo_map: dict[int, float] = {}
        correct_1x2 = 0
        brier_sum = 0.0
        log_loss_sum = 0.0
        bins = {i: {"count": 0, "pred_sum": 0.0, "actual_sum": 0.0} for i in range(5)}

        for m in matches:
            if m.home_team_id not in elo_map:
                elo_map[m.home_team_id] = initial_elo
            if m.away_team_id not in elo_map:
                elo_map[m.away_team_id] = initial_elo

            pred = generate_prediction_for_match(m, db=db, elo_lookup=elo_map)
            probs = (pred["prob_home"], pred["prob_draw"], pred["prob_away"])

            if m.home_score > m.away_score:
                actual_idx = 0
                outcome = (1.0, 0.0, 0.0)
            elif m.home_score == m.away_score:
                actual_idx = 1
                outcome = (0.0, 1.0, 0.0)
            else:
                actual_idx = 2
                outcome = (0.0, 0.0, 1.0)

            pred_idx = max(range(3), key=lambda idx: probs[idx])
            if pred_idx == actual_idx:
                correct_1x2 += 1

            brier_sum += sum((probs[i] - outcome[i]) ** 2 for i in range(3))
            log_loss_sum += -math.log(max(1e-6, probs[actual_idx]))

            max_p = probs[pred_idx]
            bin_idx = min(4, int(max_p * 5))
            bins[bin_idx]["count"] += 1
            bins[bin_idx]["pred_sum"] += max_p
            bins[bin_idx]["actual_sum"] += 1.0 if pred_idx == actual_idx else 0.0

            # Update Elo hanya setelah hasil pertandingan diketahui
            new_h, new_a = update_elo(elo_map[m.home_team_id], elo_map[m.away_team_id], m.home_score, m.away_score)
            elo_map[m.home_team_id] = new_h
            elo_map[m.away_team_id] = new_a

        n = len(matches)
        calibration = []
        for idx, b in bins.items():
            if b["count"] > 0:
                calibration.append({
                    "bin": f"{idx*20}-{(idx+1)*20}%",
                    "count": b["count"],
                    "avg_pred": round(b["pred_sum"] / b["count"], 3),
                    "actual_freq": round(b["actual_sum"] / b["count"], 3),
                })

        report = {
            "model_version": MODEL_VERSION,
            "total_matches": n,
            "accuracy_1x2": round((correct_1x2 / n) * 100, 2),
            "brier_score": round(brier_sum / n, 4),
            "log_loss": round(log_loss_sum / n, 4),
            "calibration": calibration,
        }
        print(f"=== LAPORAN BACKTEST WALK-FORWARD ({MODEL_VERSION}) ===")
        print(f"Total Laga Dievaluasi : {report['total_matches']}")
        print(f"Akurasi 1X2           : {report['accuracy_1x2']}%")
        print(f"Brier Score (lebih kecil lebih baik): {report['brier_score']}")
        print(f"Log Loss (lebih kecil lebih baik)   : {report['log_loss']}")
        print(f"Kalibrasi             : {report['calibration']}")
        return report
    finally:
        db.close()


if __name__ == "__main__":
    run_backtest()
