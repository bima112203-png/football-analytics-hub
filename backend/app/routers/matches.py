from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import cache, get_db
from app.models import Match, Team
from app.schemas import MatchDetailOut, MatchOut
from app.services.ingestion import sync_league_data

router = APIRouter(tags=["Pertandingan & Ingestion"])


def _serialize_recent(m: Match, team_id: int) -> dict:
    is_home = m.home_team_id == team_id
    gf = m.home_score if is_home else m.away_score
    ga = m.away_score if is_home else m.home_score
    opponent = m.away_team.name if is_home else m.home_team.name
    if gf is None or ga is None:
        res = "-"
    elif gf > ga:
        res = "W"
    elif gf == ga:
        res = "D"
    else:
        res = "L"
    return {
        "match_id": m.id,
        "date": m.match_date.isoformat(),
        "opponent": opponent,
        "is_home": is_home,
        "goals_for": gf,
        "goals_against": ga,
        "result": res,
    }


@router.get("/matches", response_model=list[MatchOut])
def list_matches(
    league: Optional[str] = Query(default=None, description="Kode liga: PL, PD, SA, BL1"),
    date_from: Optional[str] = Query(default=None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(default=None, description="ISO date YYYY-MM-DD"),
    status: Optional[str] = Query(default=None, description="SCHEDULED, LIVE, FINISHED"),
    db: Session = Depends(get_db),
):
    cache_key = f"matches:list:{league}:{date_from}:{date_to}:{status}"
    cached = cache.get_json(cache_key)
    if cached is not None:
        return cached

    query = db.query(Match).options(
        joinedload(Match.home_team).joinedload(Team.stats),
        joinedload(Match.away_team).joinedload(Team.stats),
        joinedload(Match.prediction),
    )

    if league:
        query = query.filter(Match.league_code == league.upper())

    if status:
        query = query.filter(Match.status == status.upper())
    elif not date_from and not date_to:
        now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now + timedelta(days=8)
        query = query.filter(Match.match_date >= now, Match.match_date <= end)

    if date_from:
        dt_from = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        query = query.filter(Match.match_date >= dt_from)
    if date_to:
        dt_to = datetime.fromisoformat(date_to).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        query = query.filter(Match.match_date <= dt_to)

    rows = query.order_by(Match.match_date.asc()).all()
    serialized = [MatchOut.model_validate(r).model_dump(mode="json") for r in rows]
    cache.set_json(cache_key, serialized, ttl_seconds=300)
    return serialized


@router.get("/matches/{match_id}", response_model=MatchDetailOut)
def get_match_detail(match_id: int, db: Session = Depends(get_db)):
    cache_key = f"matches:detail:{match_id}"
    cached = cache.get_json(cache_key)
    if cached is not None:
        return cached

    match = (
        db.query(Match)
        .options(
            joinedload(Match.home_team).joinedload(Team.stats),
            joinedload(Match.away_team).joinedload(Team.stats),
            joinedload(Match.prediction),
        )
        .filter(Match.id == match_id)
        .first()
    )
    if not match:
        raise HTTPException(status_code=404, detail="Pertandingan tidak ditemukan.")

    h2h_rows = (
        db.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.status == "FINISHED",
            Match.id != match.id,
            or_(
                (Match.home_team_id == match.home_team_id) & (Match.away_team_id == match.away_team_id),
                (Match.home_team_id == match.away_team_id) & (Match.away_team_id == match.home_team_id),
            ),
        )
        .order_by(Match.match_date.desc())
        .limit(10)
        .all()
    )

    home_recent_rows = (
        db.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.status == "FINISHED",
            or_(Match.home_team_id == match.home_team_id, Match.away_team_id == match.home_team_id),
        )
        .order_by(Match.match_date.desc())
        .limit(10)
        .all()
    )

    away_recent_rows = (
        db.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.status == "FINISHED",
            or_(Match.home_team_id == match.away_team_id, Match.away_team_id == match.away_team_id),
        )
        .order_by(Match.match_date.desc())
        .limit(10)
        .all()
    )

    base = MatchOut.model_validate(match).model_dump(mode="json")
    detail = {
        **base,
        "injuries_json": match.injuries_json or {"home": [], "away": []},
        "head_to_head": [
            {
                "match_id": h.id,
                "date": h.match_date.isoformat(),
                "home_team": h.home_team.name,
                "away_team": h.away_team.name,
                "home_score": h.home_score,
                "away_score": h.away_score,
            }
            for h in h2h_rows
        ],
        "home_recent_matches": [_serialize_recent(r, match.home_team_id) for r in home_recent_rows],
        "away_recent_matches": [_serialize_recent(r, match.away_team_id) for r in away_recent_rows],
    }
    cache.set_json(cache_key, detail, ttl_seconds=300)
    return detail


@router.get("/standings")
def get_standings(
    league: str = Query(default="PL", description="Kode liga: PL, PD, SA, BL1"),
    db: Session = Depends(get_db),
):
    code = league.upper()
    teams = (
        db.query(Team)
        .options(joinedload(Team.stats))
        .filter(Team.league_code == code)
        .all()
    )
    rows = []
    for t in teams:
        st = t.stats
        played = st.played if st else 0
        wins = st.wins if st else 0
        draws = st.draws if st else 0
        losses = st.losses if st else 0
        gf = st.goals_for if st else 0
        ga = st.goals_against if st else 0
        pts = wins * 3 + draws
        rows.append({
            "team_id": t.id,
            "name": t.name,
            "short_name": t.short_name,
            "crest_url": t.crest_url,
            "league_code": t.league_code,
            "elo_rating": round(t.elo_rating, 1),
            "played": played,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": gf,
            "goals_against": ga,
            "goal_diff": gf - ga,
            "points": pts,
            "xg_for_avg": st.xg_for_avg if st else None,
            "recent_form": st.recent_form if st else "",
        })
    rows.sort(key=lambda r: (r["points"], r["goal_diff"], r["goals_for"]), reverse=True)
    for idx, r in enumerate(rows, start=1):
        r["position"] = idx
    return rows


@router.post("/ingest/sync")
def trigger_sync(db: Session = Depends(get_db)):
    return sync_league_data(db)
