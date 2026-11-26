from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class RawTeam:
    external_id: str
    name: str
    short_name: str
    league_code: str
    crest_url: Optional[str] = None
    initial_elo: float = 1500.0
    stats: Optional[dict[str, Any]] = None


@dataclass
class RawMatch:
    external_id: str
    league_code: str
    league_name: str
    match_date: datetime
    status: str  # SCHEDULED | LIVE | FINISHED
    home_team_ext_id: str
    away_team_ext_id: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    venue: Optional[str] = None
    injuries_json: Optional[dict[str, Any]] = None


class FootballDataProvider(ABC):
    """Interface adapter sumber data sepak bola agar mudah ditukar antar provider."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Nama identifikasi provider."""

    @abstractmethod
    def fetch_teams(self, league_code: str) -> list[RawTeam]:
        """Mengambil daftar tim pada sebuah liga."""

    @abstractmethod
    def fetch_matches(self, league_code: str, days_ahead: int = 7) -> list[RawMatch]:
        """Mengambil jadwal dan hasil pertandingan."""
