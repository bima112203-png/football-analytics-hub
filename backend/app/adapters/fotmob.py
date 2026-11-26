from datetime import datetime, timedelta, timezone
from typing import Optional

from app.adapters.base import FootballDataProvider, RawMatch, RawTeam
from app.adapters.mock_seed import LEAGUE_NAMES
from app.services.normalizer import normalize_status, normalize_team_name
from app.services.resilience import CircuitBreaker, RateLimiter, ResilientHttpClient

FOTMOB_LEAGUE_IDS = {
    "PL": 47,     # Premier League (Inggris)
    "PD": 87,     # La Liga (Spanyol)
    "SA": 55,     # Serie A (Italia)
    "BL1": 54,    # Bundesliga (Jerman)
    "FL1": 53,    # Ligue 1 (Prancis)
    "CL": 42,     # UEFA Champions League
    "EL": 73,     # UEFA Europa League
    "DED": 57,    # Eredivisie (Belanda)
    "PPL": 61,    # Liga Portugal
    "ELC": 48,    # Championship (Inggris)
    "ID1": 8983,  # Super League / Liga 1 (Indonesia)
    "TUR": 71,    # Süper Lig (Turki)
    "BRA": 268,   # Brasileirão Série A (Brasil)
    "USA": 130,   # MLS (Amerika Serikat)
    "JPN": 223,   # J1 League (Jepang)
}

_fotmob_limiter = RateLimiter(max_calls=45, period_seconds=60.0)
_fotmob_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60.0)


class FotMobAdapter(FootballDataProvider):
    """Adapter live untuk FotMob (/api/data/leagues) dengan rate limiter, retry, ETag, dan circuit breaker."""

    BASE_URL = "https://www.fotmob.com/api/data"

    def __init__(self, http_client: Optional[ResilientHttpClient] = None):
        self._http = http_client or ResilientHttpClient(
            name="fotmob",
            rate_limiter=_fotmob_limiter,
            circuit_breaker=_fotmob_breaker,
            max_retries=2,
            base_delay=0.4,
            timeout=15.0,
        )
        self._league_cache: dict[str, dict] = {}
        self.last_etag: Optional[str] = None
        self.not_modified: bool = False

    @property
    def provider_name(self) -> str:
        return "fotmob"

    def _get_league_data(self, league_code: str, etag: Optional[str] = None) -> Optional[dict]:
        if league_code in self._league_cache:
            return self._league_cache[league_code]
        league_id = FOTMOB_LEAGUE_IDS.get(league_code)
        if not league_id:
            return None

        data, not_mod, headers = self._http.get_json(
            f"{self.BASE_URL}/leagues",
            headers={"User-Agent": "Mozilla/5.0"},
            params={"id": league_id},
            etag=etag,
        )
        if not_mod:
            self.not_modified = True
            return None
        if not isinstance(data, dict):
            raise ValueError("Respons FotMob bukan objek JSON valid")

        self.last_etag = headers.get("etag") or headers.get("ETag")
        self._league_cache[league_code] = data
        return data

    def _extract_table_rows(self, data: dict) -> list[dict]:
        table_list = data.get("table") or []
        if not table_list:
            return []
        t_data = table_list[0].get("data", {})
        # Format standar liga
        rows = t_data.get("table", {}).get("all", [])
        if rows:
            return rows
        # Format kompetisi grup / fase liga (CL, EL)
        merged: list[dict] = []
        for grp in t_data.get("tables", []):
            merged.extend(grp.get("table", {}).get("all", []))
        return merged

    def fetch_teams(self, league_code: str) -> list[RawTeam]:
        data = self._get_league_data(league_code)
        if not data:
            return []

        table_rows = self._extract_table_rows(data)
        if not table_rows:
            return []

        teams: list[RawTeam] = []
        seen_ids: set[str] = set()
        for row in table_rows:
            ext_id = f"fm-{row['id']}"
            if ext_id in seen_ids:
                continue
            seen_ids.add(ext_id)

            played = max(1, int(row.get("played") or 1))
            wins = int(row.get("wins") or 0)
            draws = int(row.get("draws") or 0)
            losses = int(row.get("losses") or 0)
            pts = int(row.get("pts") or 0)

            scores_str = str(row.get("scoresStr") or "0-0")
            parts = [p.strip() for p in scores_str.split("-")]
            gf = int(parts[0]) if len(parts) == 2 and parts[0].isdigit() else played
            ga = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else played

            ppg = pts / played
            elo = round(1450.0 + (ppg * 165.0), 1)
            gf_avg = round(gf / played, 2)
            ga_avg = round(ga / played, 2)

            norm_name = normalize_team_name(row["name"])
            short = (row.get("shortName") or norm_name[:3]).upper()[:10]
            teams.append(
                RawTeam(
                    external_id=ext_id,
                    name=norm_name,
                    short_name=short,
                    league_code=league_code,
                    crest_url=f"https://images.fotmob.com/image_resources/logo/teamlogo/{row['id']}.png",
                    initial_elo=elo,
                    stats={
                        "season": "2026/2027",
                        "played": played,
                        "wins": wins,
                        "draws": draws,
                        "losses": losses,
                        "goals_for": gf,
                        "goals_against": ga,
                        "xg_for_avg": gf_avg,
                        "xg_against_avg": ga_avg,
                        "shots_avg": round(10.5 + gf_avg * 2.8, 1),
                        "possession_avg": round(46.0 + ppg * 6.5, 1),
                        "home_attack_strength": round(max(0.5, gf_avg / 1.40), 3),
                        "home_defense_strength": round(max(0.5, ga_avg / 1.30), 3),
                        "away_attack_strength": round(max(0.5, (gf_avg * 0.90) / 1.25), 3),
                        "away_defense_strength": round(max(0.5, (ga_avg * 1.10) / 1.35), 3),
                        "recent_form": "W" * min(3, wins) + "D" * min(1, draws) + "L" * min(1, losses),
                    },
                )
            )
        return teams

    def fetch_matches(self, league_code: str, days_ahead: int = 7) -> list[RawMatch]:
        data = self._get_league_data(league_code)
        if not data:
            return []

        all_matches = data.get("fixtures", {}).get("allMatches", [])
        if not isinstance(all_matches, list):
            return []

        league_name = data.get("details", {}).get("name") or LEAGUE_NAMES.get(league_code, league_code)
        now = datetime.now(timezone.utc)
        past_cutoff = now - timedelta(days=45)
        future_cutoff = now + timedelta(days=days_ahead + 1)

        matches: list[RawMatch] = []
        for m in all_matches:
            st = m.get("status", {})
            utc_str = st.get("utcTime")
            if not utc_str:
                continue
            m_date = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
            if m_date < past_cutoff or m_date > future_cutoff:
                continue

            finished = bool(st.get("finished"))
            started = bool(st.get("started"))
            cancelled = bool(st.get("cancelled"))
            reason_key = str(st.get("reason", {}).get("shortKey", "")).lower()

            if cancelled:
                status = "CANCELLED"
            elif "postponed" in reason_key or "abandoned" in reason_key:
                status = normalize_status(reason_key)
            elif finished:
                status = "FINISHED"
            elif started:
                status = "LIVE"
            else:
                status = "SCHEDULED"

            hs, as_ = None, None
            if finished and st.get("scoreStr"):
                sp = [x.strip() for x in str(st["scoreStr"]).split("-")]
                if len(sp) == 2 and sp[0].isdigit() and sp[1].isdigit():
                    hs, as_ = int(sp[0]), int(sp[1])

            matches.append(
                RawMatch(
                    external_id=f"fm-m-{m['id']}",
                    league_code=league_code,
                    league_name=league_name,
                    match_date=m_date,
                    status=status,
                    home_team_ext_id=f"fm-{m['home']['id']}",
                    away_team_ext_id=f"fm-{m['away']['id']}",
                    home_score=hs,
                    away_score=as_,
                    venue=None,
                )
            )
        return matches
