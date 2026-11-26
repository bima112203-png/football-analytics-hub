from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session, joinedload

from app.adapters import get_provider
from app.adapters.base import FootballDataProvider
from app.database import cache
from app.logging_config import get_logger
from app.ml.predictor import upsert_prediction
from app.models import Match, SyncLog, Team, TeamStat
from app.services.events import event_bus
from app.services.normalizer import ensure_utc_dt, normalize_league, normalize_status, normalize_team_name
from app.services.resilience import ValidatedRawMatch, ValidatedRawTeam

logger = get_logger("ingestion")
DEFAULT_LEAGUES = ["PL", "PD", "SA", "BL1", "FL1", "CL", "EL", "DED", "PPL", "ELC", "ID1", "TUR", "BRA", "USA", "JPN"]


def sync_league_data(
    db: Session,
    leagues: Optional[list[str]] = None,
    days_ahead: int = 7,
    job_type: str = "manual",
    provider_override: Optional[FootballDataProvider] = None,
    recalculate_predictions: bool = True,
) -> dict:
    """Sinkronisasi idempoten tim, statistik, dan pertandingan dengan validasi & sync_log."""
    provider = provider_override or get_provider()
    target_leagues = leagues or DEFAULT_LEAGUES
    started_at = datetime.now(timezone.utc)

    log_entry = SyncLog(
        started_at=started_at,
        source=provider.provider_name,
        job_type=job_type,
        status="running",
        records_upserted=0,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)

    teams_upserted = 0
    matches_upserted = 0
    predictions_updated = 0
    validation_errors: list[str] = []
    touched_match_ids: list[int] = []

    try:
        for league_code in target_leagues:
            raw_teams = provider.fetch_teams(league_code)
            team_map: dict[str, Team] = {}

            for rt in raw_teams:
                try:
                    v_team = ValidatedRawTeam(
                        external_id=rt.external_id,
                        name=normalize_team_name(rt.name),
                        short_name=rt.short_name,
                        league_code=rt.league_code,
                        crest_url=rt.crest_url,
                        initial_elo=rt.initial_elo,
                    )
                except ValidationError as ve:
                    validation_errors.append(f"Team invalid ({rt.external_id}): {ve.errors()[0]['msg']}")
                    continue

                team = db.query(Team).filter(Team.external_id == v_team.external_id).first()
                if not team:
                    team = Team(
                        external_id=v_team.external_id,
                        name=v_team.name,
                        short_name=v_team.short_name,
                        crest_url=v_team.crest_url,
                        league_code=v_team.league_code,
                        elo_rating=v_team.initial_elo,
                    )
                    db.add(team)
                    db.flush()
                else:
                    team.name = v_team.name
                    team.short_name = v_team.short_name
                    if v_team.crest_url:
                        team.crest_url = v_team.crest_url

                if rt.stats:
                    stat = db.query(TeamStat).filter(TeamStat.team_id == team.id).first()
                    if not stat:
                        stat = TeamStat(team_id=team.id, **rt.stats)
                        db.add(stat)
                    else:
                        for k, v in rt.stats.items():
                            setattr(stat, k, v)

                team_map[v_team.external_id] = team
                teams_upserted += 1

            raw_matches = provider.fetch_matches(league_code, days_ahead=days_ahead)
            for rm in raw_matches:
                norm_code, norm_name = normalize_league(rm.league_code, rm.league_name)
                norm_st = normalize_status(rm.status)
                try:
                    v_match = ValidatedRawMatch(
                        external_id=rm.external_id,
                        league_code=norm_code,
                        league_name=norm_name,
                        match_date=rm.match_date,
                        status=norm_st,
                        home_team_ext_id=rm.home_team_ext_id,
                        away_team_ext_id=rm.away_team_ext_id,
                        home_score=rm.home_score,
                        away_score=rm.away_score,
                    )
                except ValidationError as ve:
                    validation_errors.append(f"Match invalid ({rm.external_id}): {ve.errors()[0]['msg']}")
                    continue

                home_team = team_map.get(v_match.home_team_ext_id) or db.query(Team).filter(
                    Team.external_id == v_match.home_team_ext_id
                ).first()
                away_team = team_map.get(v_match.away_team_ext_id) or db.query(Team).filter(
                    Team.external_id == v_match.away_team_ext_id
                ).first()
                if not home_team or not away_team:
                    continue

                match = db.query(Match).filter(Match.external_id == v_match.external_id).first()
                if not match:
                    match = Match(
                        external_id=v_match.external_id,
                        league_code=v_match.league_code,
                        league_name=v_match.league_name,
                        match_date=ensure_utc_dt(v_match.match_date),
                        status=v_match.status,
                        home_team_id=home_team.id,
                        away_team_id=away_team.id,
                        home_score=v_match.home_score,
                        away_score=v_match.away_score,
                        venue=rm.venue,
                        injuries_json=rm.injuries_json,
                    )
                    db.add(match)
                    db.flush()
                else:
                    match.league_code = v_match.league_code
                    match.league_name = v_match.league_name
                    match.match_date = ensure_utc_dt(v_match.match_date)
                    match.status = v_match.status
                    match.home_score = v_match.home_score
                    match.away_score = v_match.away_score
                    if rm.injuries_json is not None:
                        match.injuries_json = rm.injuries_json

                touched_match_ids.append(match.id)
                matches_upserted += 1

        db.commit()

        if recalculate_predictions and touched_match_ids:
            matches_to_pred = (
                db.query(Match)
                .options(
                    joinedload(Match.home_team).joinedload(Team.stats),
                    joinedload(Match.away_team).joinedload(Team.stats),
                )
                .filter(Match.id.in_(touched_match_ids))
                .all()
            )
            for m in matches_to_pred:
                upsert_prediction(db, m)
                predictions_updated += 1

        final_status = "partial" if validation_errors else "success"
        if getattr(provider, "not_modified", False) and matches_upserted == 0 and teams_upserted == 0:
            final_status = "not_modified"

        log_entry.finished_at = datetime.now(timezone.utc)
        log_entry.status = final_status
        log_entry.records_upserted = teams_upserted + matches_upserted
        log_entry.etag = getattr(provider, "last_etag", None)
        if validation_errors:
            log_entry.error_message = "; ".join(validation_errors[:5])
        db.commit()

        cache.delete_prefix("matches:")
        cache.delete_prefix("predict:")

        result = {
            "provider": provider.provider_name,
            "job_type": job_type,
            "status": final_status,
            "data_delayed": False,
            "leagues": target_leagues,
            "teams_upserted": teams_upserted,
            "matches_upserted": matches_upserted,
            "predictions_updated": predictions_updated,
            "validation_errors_count": len(validation_errors),
        }
        logger.info("Sinkronisasi selesai", extra={"extra_data": result})
        event_bus.publish("sync_complete", result)
        return result

    except Exception as exc:
        db.rollback()
        log_entry.finished_at = datetime.now(timezone.utc)
        log_entry.status = "failed"
        log_entry.records_upserted = 0
        log_entry.error_message = str(exc)[:1000]
        db.add(log_entry)
        db.commit()

        logger.error(
            "Sinkronisasi gagal; data valid terakhir dipertahankan",
            extra={"extra_data": {"provider": provider.provider_name, "job_type": job_type, "error": str(exc)}},
        )
        return {
            "provider": provider.provider_name,
            "job_type": job_type,
            "status": "failed",
            "data_delayed": True,
            "error": str(exc),
            "teams_upserted": 0,
            "matches_upserted": 0,
            "predictions_updated": 0,
        }


def get_sync_status(db: Session) -> dict:
    """Mengambil ringkasan status sinkronisasi terakhir dan penanda keterlambatan data."""
    latest = db.query(SyncLog).order_by(SyncLog.id.desc()).first()
    last_ok = (
        db.query(SyncLog)
        .filter(SyncLog.status.in_(["success", "not_modified", "partial"]))
        .order_by(SyncLog.id.desc())
        .first()
    )
    if not latest:
        return {
            "data_delayed": False,
            "delay_label": None,
            "last_sync_status": None,
            "last_sync_at": None,
            "last_success_at": None,
            "source": None,
        }

    is_delayed = latest.status == "failed"
    now = datetime.now(timezone.utc)
    ref_time = last_ok.finished_at or last_ok.started_at if last_ok else latest.started_at
    if ref_time.tzinfo is None:
        ref_time = ref_time.replace(tzinfo=timezone.utc)
    age_minutes = max(0, int((now - ref_time).total_seconds() // 60))

    return {
        "data_delayed": is_delayed,
        "delay_label": "Data mungkin tertunda" if is_delayed else None,
        "last_sync_status": latest.status,
        "last_sync_at": latest.started_at.isoformat(),
        "last_success_at": ref_time.isoformat(),
        "last_sync_age_minutes": age_minutes,
        "source": latest.source,
        "last_error": latest.error_message if is_delayed else None,
    }
