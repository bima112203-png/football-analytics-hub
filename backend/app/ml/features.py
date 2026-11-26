import math
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Match, Team


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_team_context_features(
    db: Optional[Session],
    team: Team,
    before_date: datetime,
    injuries_list: Optional[list[dict]] = None,
    elo_lookup: Optional[dict[int, float]] = None,
) -> dict:
    """
    Menghitung fitur kontekstual tim secara kronologis (strictly before_date, bebas data leakage):
    - rest_days: hari istirahat sejak laga terakhir
    - weighted_form: skor form berbobot recency (0..1)
    - sos_elo: rata-rata Elo lawan pada 6 laga terakhir (kekuatan jadwal)
    - injury_penalty: penalti dampak cedera (0.0 .. 0.15)
    """
    ref_dt = _ensure_utc(before_date)
    rest_days = 7.0
    weighted_form = 0.55
    sos_elo = 1550.0

    if db is not None:
        past_matches = (
            db.query(Match)
            .filter(
                Match.status == "FINISHED",
                Match.match_date < ref_dt,
                Match.home_score.isnot(None),
                Match.away_score.isnot(None),
                or_(Match.home_team_id == team.id, Match.away_team_id == team.id),
            )
            .order_by(Match.match_date.desc())
            .limit(8)
            .all()
        )

        if past_matches:
            last_dt = _ensure_utc(past_matches[0].match_date)
            rest_days = round(max(1.0, min(21.0, (ref_dt - last_dt).total_seconds() / 86400.0)), 1)

            w_sum = 0.0
            score_sum = 0.0
            opp_elos: list[float] = []

            for idx, pm in enumerate(past_matches):
                decay = math.exp(-0.25 * idx)
                is_home = pm.home_team_id == team.id
                gf = pm.home_score if is_home else pm.away_score
                ga = pm.away_score if is_home else pm.home_score
                pts_norm = 1.0 if gf > ga else (0.5 if gf == ga else 0.0)
                score_sum += decay * pts_norm
                w_sum += decay

                opp_id = pm.away_team_id if is_home else pm.home_team_id
                if elo_lookup and opp_id in elo_lookup:
                    opp_elos.append(elo_lookup[opp_id])
                else:
                    opp_team = pm.away_team if is_home else pm.home_team
                    if opp_team:
                        opp_elos.append(opp_team.elo_rating)

            if w_sum > 0:
                weighted_form = round(score_sum / w_sum, 3)
            if opp_elos:
                sos_elo = round(sum(opp_elos) / len(opp_elos), 1)

    injury_penalty = 0.0
    if injuries_list:
        for inj in injuries_list:
            st = str(inj.get("status", "")).lower()
            if "absen" in st or "out" in st:
                injury_penalty += 0.04
            elif "diragukan" in st or "doubt" in st:
                injury_penalty += 0.02
    injury_penalty = round(min(0.15, injury_penalty), 3)

    return {
        "rest_days": rest_days,
        "weighted_form": weighted_form,
        "sos_elo": sos_elo,
        "injury_penalty": injury_penalty,
    }
