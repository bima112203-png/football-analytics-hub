from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    password_hash = Column(String(255), nullable=True)
    auth_provider = Column(String(30), nullable=False, default="email")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    simulations = relationship("Simulation", back_populates="user")


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(80), unique=True, nullable=False, index=True)
    name = Column(String(150), nullable=False)
    short_name = Column(String(30), nullable=False)
    crest_url = Column(String(500), nullable=True)
    league_code = Column(String(20), nullable=False, index=True)
    elo_rating = Column(Float, nullable=False, default=1500.0)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    stats = relationship("TeamStat", back_populates="team", uselist=False)


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(80), unique=True, nullable=False, index=True)
    league_code = Column(String(20), nullable=False, index=True)
    league_name = Column(String(120), nullable=False)
    match_date = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(30), nullable=False, default="SCHEDULED", index=True)

    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)

    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    venue = Column(String(150), nullable=True)
    injuries_json = Column(JSON, nullable=True)

    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    prediction = relationship("Prediction", back_populates="match", uselist=False)


class TeamStat(Base):
    __tablename__ = "team_stats"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), unique=True, nullable=False)
    season = Column(String(20), nullable=False, default="2025/2026")
    played = Column(Integer, nullable=False, default=0)
    wins = Column(Integer, nullable=False, default=0)
    draws = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    goals_for = Column(Integer, nullable=False, default=0)
    goals_against = Column(Integer, nullable=False, default=0)
    xg_for_avg = Column(Float, nullable=False, default=1.35)
    xg_against_avg = Column(Float, nullable=False, default=1.25)
    shots_avg = Column(Float, nullable=False, default=12.0)
    possession_avg = Column(Float, nullable=False, default=50.0)
    home_attack_strength = Column(Float, nullable=False, default=1.0)
    home_defense_strength = Column(Float, nullable=False, default=1.0)
    away_attack_strength = Column(Float, nullable=False, default=1.0)
    away_defense_strength = Column(Float, nullable=False, default=1.0)
    recent_form = Column(String(20), nullable=False, default="WDLWD")
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    team = relationship("Team", back_populates="stats")


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id"), unique=True, nullable=False)
    model_version = Column(String(50), nullable=False, default="dixon-coles-elo-v1")

    prob_home = Column(Float, nullable=False)
    prob_draw = Column(Float, nullable=False)
    prob_away = Column(Float, nullable=False)
    prob_over_25 = Column(Float, nullable=False)
    prob_under_25 = Column(Float, nullable=False)
    prob_btts_yes = Column(Float, nullable=False)
    prob_btts_no = Column(Float, nullable=False)

    expected_home_goals = Column(Float, nullable=False)
    expected_away_goals = Column(Float, nullable=False)
    predicted_home_score = Column(Integer, nullable=False)
    predicted_away_score = Column(Integer, nullable=False)
    confidence_score = Column(Float, nullable=False)
    explanation_text = Column(Text, nullable=False)
    is_correct_1x2 = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    match = relationship("Match", back_populates="prediction")


class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(150), nullable=False)
    legs_json = Column(JSON, nullable=False)
    combined_probability = Column(Float, nullable=False)
    combined_odds = Column(Float, nullable=True)
    expected_value = Column(Float, nullable=True)
    risk_level = Column(String(30), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="simulations")


class SyncLog(Base):
    __tablename__ = "sync_log"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(String(50), nullable=False, index=True)
    job_type = Column(String(40), nullable=False, default="manual")  # daily | live_poll | manual
    status = Column(String(30), nullable=False)  # success | not_modified | failed | partial
    records_upserted = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    etag = Column(String(255), nullable=True)
