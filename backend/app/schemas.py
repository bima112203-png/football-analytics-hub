from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict


class TeamStatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    season: str
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    xg_for_avg: float
    xg_against_avg: float
    shots_avg: float
    possession_avg: float
    home_attack_strength: float
    home_defense_strength: float
    away_attack_strength: float
    away_defense_strength: float
    recent_form: str


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    name: str
    short_name: str
    crest_url: Optional[str] = None
    league_code: str
    elo_rating: float
    stats: Optional[TeamStatOut] = None


class PredictionSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    model_version: str
    prob_home: float
    prob_draw: float
    prob_away: float
    prob_over_25: float
    prob_under_25: float
    prob_btts_yes: float
    prob_btts_no: float
    expected_home_goals: float
    expected_away_goals: float
    predicted_home_score: int
    predicted_away_score: int
    confidence_score: float
    explanation_text: str


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    external_id: str
    league_code: str
    league_name: str
    match_date: datetime
    status: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    venue: Optional[str] = None
    home_team: TeamOut
    away_team: TeamOut
    prediction: Optional[PredictionSummaryOut] = None


class MatchDetailOut(MatchOut):
    injuries_json: Optional[dict[str, Any]] = None
    head_to_head: list[dict[str, Any]] = []
    home_recent_matches: list[dict[str, Any]] = []
    away_recent_matches: list[dict[str, Any]] = []
