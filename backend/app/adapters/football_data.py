from datetime import datetime, timedelta, timezone
import httpx

from app.adapters.base import FootballDataProvider, RawMatch, RawTeam
from app.adapters.mock_seed import MockSeedAdapter


class FootballDataOrgAdapter(FootballDataProvider):
    """Adapter untuk API football-data.org v4 dengan fallback otomatis ke mock."""

    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._fallback = MockSeedAdapter()

    @property
    def provider_name(self) -> str:
        return "football-data.org"

    def _headers(self) -> dict[str, str]:
        return {"X-Auth-Token": self.api_key}

    def fetch_teams(self, league_code: str) -> list[RawTeam]:
        try:
            url = f"{self.BASE_URL}/competitions/{league_code}/teams"
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers())
                resp.raise_for_status()
                data = resp.json()

            teams: list[RawTeam] = []
            for t in data.get("teams", []):
                teams.append(
                    RawTeam(
                        external_id=f"fd-{t['id']}",
                        name=t["name"],
                        short_name=(t.get("tla") or t["shortName"] or t["name"][:3]).upper(),
                        league_code=league_code,
                        crest_url=t.get("crest"),
                        initial_elo=1550.0,
                    )
                )
            return teams or self._fallback.fetch_teams(league_code)
        except Exception:
            return self._fallback.fetch_teams(league_code)

    def fetch_matches(self, league_code: str, days_ahead: int = 7) -> list[RawMatch]:
        try:
            now = datetime.now(timezone.utc)
            date_from = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            date_to = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            url = f"{self.BASE_URL}/competitions/{league_code}/matches"
            params = {"dateFrom": date_from, "dateTo": date_to}

            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, headers=self._headers(), params=params)
                resp.raise_for_status()
                data = resp.json()

            league_name = data.get("competition", {}).get("name", league_code)
            matches: list[RawMatch] = []
            for m in data.get("matches", []):
                ft = m.get("score", {}).get("fullTime", {})
                status = m.get("status", "SCHEDULED")
                if status not in ("SCHEDULED", "TIMED", "IN_PLAY", "PAUSED", "FINISHED"):
                    status = "SCHEDULED"
                if status in ("TIMED",):
                    status = "SCHEDULED"
                if status in ("IN_PLAY", "PAUSED"):
                    status = "LIVE"

                matches.append(
                    RawMatch(
                        external_id=f"fd-m-{m['id']}",
                        league_code=league_code,
                        league_name=league_name,
                        match_date=datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")),
                        status=status,
                        home_team_ext_id=f"fd-{m['homeTeam']['id']}",
                        away_team_ext_id=f"fd-{m['awayTeam']['id']}",
                        home_score=ft.get("home"),
                        away_score=ft.get("away"),
                        venue=m.get("venue"),
                    )
                )
            return matches or self._fallback.fetch_matches(league_code, days_ahead)
        except Exception:
            return self._fallback.fetch_matches(league_code, days_ahead)
