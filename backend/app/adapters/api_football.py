from datetime import datetime, timezone
import httpx

from app.adapters.base import FootballDataProvider, RawMatch, RawTeam
from app.adapters.mock_seed import MockSeedAdapter

API_FOOTBALL_LEAGUE_IDS = {
    "PL": 39,
    "PD": 140,
    "SA": 135,
    "BL1": 78,
}


class ApiFootballAdapter(FootballDataProvider):
    """Adapter alternatif untuk API-Football (api-sports.io) dengan fallback ke mock."""

    BASE_URL = "https://v3.football.api-sports.io"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._fallback = MockSeedAdapter()

    @property
    def provider_name(self) -> str:
        return "api-football"

    def _headers(self) -> dict[str, str]:
        return {"x-apisports-key": self.api_key}

    def fetch_teams(self, league_code: str) -> list[RawTeam]:
        league_id = API_FOOTBALL_LEAGUE_IDS.get(league_code)
        if not league_id:
            return self._fallback.fetch_teams(league_code)
        try:
            url = f"{self.BASE_URL}/teams"
            params = {"league": league_id, "season": 2025}
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers(), params=params)
                resp.raise_for_status()
                data = resp.json()

            teams: list[RawTeam] = []
            for item in data.get("response", []):
                t = item["team"]
                teams.append(
                    RawTeam(
                        external_id=f"af-{t['id']}",
                        name=t["name"],
                        short_name=(t.get("code") or t["name"][:3]).upper(),
                        league_code=league_code,
                        crest_url=t.get("logo"),
                        initial_elo=1550.0,
                    )
                )
            return teams or self._fallback.fetch_teams(league_code)
        except Exception:
            return self._fallback.fetch_teams(league_code)

    def fetch_matches(self, league_code: str, days_ahead: int = 7) -> list[RawMatch]:
        league_id = API_FOOTBALL_LEAGUE_IDS.get(league_code)
        if not league_id:
            return self._fallback.fetch_matches(league_code, days_ahead)
        try:
            url = f"{self.BASE_URL}/fixtures"
            params = {"league": league_id, "season": 2025, "next": 15}
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers(), params=params)
                resp.raise_for_status()
                data = resp.json()

            matches: list[RawMatch] = []
            for item in data.get("response", []):
                fx = item["fixture"]
                lg = item["league"]
                tm = item["teams"]
                goals = item["goals"]
                short_status = fx.get("status", {}).get("short", "NS")
                status = "FINISHED" if short_status in ("FT", "AET", "PEN") else "SCHEDULED"
                matches.append(
                    RawMatch(
                        external_id=f"af-m-{fx['id']}",
                        league_code=league_code,
                        league_name=lg.get("name", league_code),
                        match_date=datetime.fromtimestamp(fx["timestamp"], tz=timezone.utc),
                        status=status,
                        home_team_ext_id=f"af-{tm['home']['id']}",
                        away_team_ext_id=f"af-{tm['away']['id']}",
                        home_score=goals.get("home"),
                        away_score=goals.get("away"),
                        venue=fx.get("venue", {}).get("name"),
                    )
                )
            return matches or self._fallback.fetch_matches(league_code, days_ahead)
        except Exception:
            return self._fallback.fetch_matches(league_code, days_ahead)
