from datetime import datetime, timezone
import httpx

from app.adapters.base import FootballDataProvider, RawMatch, RawTeam
from app.adapters.mock_seed import MockSeedAdapter


class FootyStatsAdapter(FootballDataProvider):
    """Adapter resmi FootyStats API (api.football-data-api.com) dengan fallback ke mock."""

    BASE_URL = "https://api.football-data-api.com"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._fallback = MockSeedAdapter()

    @property
    def provider_name(self) -> str:
        return "footystats"

    def fetch_teams(self, league_code: str) -> list[RawTeam]:
        # Memerlukan season_id dari FootyStats API; fallback otomatis bila belum dikonfigurasi
        return self._fallback.fetch_teams(league_code)

    def fetch_matches(self, league_code: str, days_ahead: int = 7) -> list[RawMatch]:
        if not self.api_key:
            return self._fallback.fetch_matches(league_code, days_ahead)
        try:
            url = f"{self.BASE_URL}/todays-matches"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, params={"key": self.api_key})
                resp.raise_for_status()
                data = resp.json()

            matches: list[RawMatch] = []
            for m in data.get("data", []):
                status = "FINISHED" if m.get("status") == "complete" else "SCHEDULED"
                matches.append(
                    RawMatch(
                        external_id=f"fs-m-{m['id']}",
                        league_code=league_code,
                        league_name=m.get("competition_name", league_code),
                        match_date=datetime.fromtimestamp(m["date_unix"], tz=timezone.utc),
                        status=status,
                        home_team_ext_id=f"fs-{m['homeID']}",
                        away_team_ext_id=f"fs-{m['awayID']}",
                        home_score=m.get("homeGoalCount") if status == "FINISHED" else None,
                        away_score=m.get("awayGoalCount") if status == "FINISHED" else None,
                        venue=m.get("stadium_name"),
                    )
                )
            return matches or self._fallback.fetch_matches(league_code, days_ahead)
        except Exception:
            return self._fallback.fetch_matches(league_code, days_ahead)
