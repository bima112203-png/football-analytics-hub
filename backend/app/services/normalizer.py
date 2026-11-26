from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

WIB_TZ = ZoneInfo("Asia/Jakarta")

LEAGUE_CANONICAL = {
    "PL": "Premier League",
    "EPL": "Premier League",
    "PD": "La Liga",
    "LL": "La Liga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "CL": "UEFA Champions League",
    "EL": "UEFA Europa League",
    "DED": "Eredivisie",
    "PPL": "Liga Portugal",
    "ELC": "Championship",
    "ID1": "BRI Liga 1 / Super League",
    "TUR": "Süper Lig",
    "BRA": "Brasileirão Série A",
    "USA": "MLS",
    "JPN": "J1 League",
}

TEAM_ALIASES = {
    "man city": "Manchester City",
    "manchester city fc": "Manchester City",
    "man united": "Manchester United",
    "man utd": "Manchester United",
    "manchester united fc": "Manchester United",
    "arsenal fc": "Arsenal",
    "chelsea fc": "Chelsea",
    "liverpool fc": "Liverpool",
    "tottenham": "Tottenham Hotspur",
    "spurs": "Tottenham Hotspur",
    "bayern munich": "Bayern München",
    "fc bayern münchen": "Bayern München",
    "inter": "Inter Milan",
    "fc internazionale milano": "Inter Milan",
    "juventus fc": "Juventus",
    "real madrid cf": "Real Madrid",
}

STATUS_MAP = {
    "SCHEDULED": "SCHEDULED",
    "TIMED": "SCHEDULED",
    "NS": "SCHEDULED",
    "NOT_STARTED": "SCHEDULED",
    "LIVE": "LIVE",
    "IN_PLAY": "LIVE",
    "PAUSED": "LIVE",
    "1H": "LIVE",
    "2H": "LIVE",
    "HT": "LIVE",
    "FINISHED": "FINISHED",
    "FT": "FINISHED",
    "AET": "FINISHED",
    "PEN": "FINISHED",
    "POSTPONED": "POSTPONED",
    "PST": "POSTPONED",
    "SUSPENDED": "POSTPONED",
    "SUSP": "POSTPONED",
    "CANCELLED": "CANCELLED",
    "CANC": "CANCELLED",
    "ABANDONED": "CANCELLED",
    "ABD": "CANCELLED",
}


def normalize_team_name(name: str) -> str:
    cleaned = " ".join(name.strip().split())
    alias = TEAM_ALIASES.get(cleaned.lower())
    return alias if alias else cleaned


def normalize_league(code: str, fallback_name: str = "") -> tuple[str, str]:
    c = code.strip().upper()
    canonical_name = LEAGUE_CANONICAL.get(c, fallback_name or c)
    return c, canonical_name


def normalize_status(raw_status: str) -> str:
    return STATUS_MAP.get(raw_status.strip().upper(), "SCHEDULED")


def ensure_utc_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_wib_iso(dt: datetime) -> str:
    utc_dt = ensure_utc_dt(dt)
    return utc_dt.astimezone(WIB_TZ).isoformat()


def format_wib_label(dt: datetime) -> str:
    utc_dt = ensure_utc_dt(dt)
    wib = utc_dt.astimezone(WIB_TZ)
    return wib.strftime("%d %b %Y, %H:%M WIB")
