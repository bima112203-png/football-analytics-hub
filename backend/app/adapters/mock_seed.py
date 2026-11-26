from datetime import datetime, timedelta, timezone
import random

from app.adapters.base import FootballDataProvider, RawMatch, RawTeam

LEAGUE_NAMES = {
    "PL": "Premier League",
    "PD": "La Liga",
    "SA": "Serie A",
    "BL1": "Bundesliga",
}

TEAMS_SEED = {
    "PL": [
        ("pl-ars", "Arsenal FC", "ARS", 1745.0, 2.15, 0.85, 16.2, 59.5, "WWWDW"),
        ("pl-mci", "Manchester City", "MCI", 1760.0, 2.25, 0.90, 17.4, 63.2, "WWLWW"),
        ("pl-liv", "Liverpool FC", "LIV", 1755.0, 2.20, 0.88, 16.8, 58.8, "WWWWL"),
        ("pl-che", "Chelsea FC", "CHE", 1650.0, 1.72, 1.15, 14.5, 56.0, "WDWLW"),
        ("pl-mun", "Manchester United", "MUN", 1615.0, 1.48, 1.28, 13.4, 52.1, "DLWLW"),
        ("pl-tot", "Tottenham Hotspur", "TOT", 1635.0, 1.78, 1.32, 14.9, 55.4, "WLWDL"),
    ],
    "PD": [
        ("pd-rma", "Real Madrid", "RMA", 1775.0, 2.30, 0.82, 16.9, 60.4, "WWWWW"),
        ("pd-bar", "FC Barcelona", "BAR", 1750.0, 2.35, 0.95, 17.1, 65.0, "WWLWW"),
        ("pd-atm", "Atlético Madrid", "ATM", 1685.0, 1.68, 0.88, 12.8, 50.2, "WDWWL"),
        ("pd-ath", "Athletic Bilbao", "ATH", 1630.0, 1.55, 1.02, 13.0, 49.8, "WDLWW"),
    ],
    "SA": [
        ("sa-int", "Inter Milan", "INT", 1740.0, 2.10, 0.78, 15.8, 57.6, "WWWDW"),
        ("sa-nap", "SSC Napoli", "NAP", 1690.0, 1.82, 0.96, 14.7, 56.2, "WDWWL"),
        ("sa-juv", "Juventus FC", "JUV", 1665.0, 1.52, 0.80, 13.2, 53.1, "DDWDW"),
        ("sa-mil", "AC Milan", "MIL", 1655.0, 1.69, 1.12, 14.1, 54.0, "WLWDW"),
    ],
    "BL1": [
        ("bl-bay", "Bayern München", "BAY", 1765.0, 2.48, 0.92, 18.2, 64.5, "WWWDW"),
        ("bl-lev", "Bayer Leverkusen", "LEV", 1735.0, 2.18, 0.94, 16.4, 59.1, "WWDWW"),
        ("bl-bvb", "Borussia Dortmund", "BVB", 1660.0, 1.85, 1.25, 14.6, 55.8, "WLWDL"),
        ("bl-rbl", "RB Leipzig", "RBL", 1650.0, 1.76, 1.18, 14.2, 53.5, "LWDWW"),
    ],
}

SAMPLE_INJURIES = [
    {"player": "Pemain Sayap Utama", "status": "Diragukan (Cedera Ringan)"},
    {"player": "Bek Tengah Inti", "status": "Absen (Pemulihan Hamstring)"},
    {"player": "Gelandang Bertahan", "status": "Siap Tampil (Kembali Latihan)"},
]


class MockSeedAdapter(FootballDataProvider):
    """Adapter data mock/seed deterministik agar sistem berjalan penuh tanpa API berbayar."""

    @property
    def provider_name(self) -> str:
        return "mock-seed"

    def fetch_teams(self, league_code: str) -> list[RawTeam]:
        items = TEAMS_SEED.get(league_code, [])
        teams: list[RawTeam] = []
        for ext_id, name, short, elo, xg_for, xg_ag, shots, poss, form in items:
            played = 12
            wins = form.count("W") * 2
            draws = form.count("D") * 2
            losses = max(0, played - wins - draws)
            teams.append(
                RawTeam(
                    external_id=ext_id,
                    name=name,
                    short_name=short,
                    league_code=league_code,
                    crest_url=None,
                    initial_elo=elo,
                    stats={
                        "season": "2025/2026",
                        "played": played,
                        "wins": wins,
                        "draws": draws,
                        "losses": losses,
                        "goals_for": int(round(xg_for * played)),
                        "goals_against": int(round(xg_ag * played)),
                        "xg_for_avg": xg_for,
                        "xg_against_avg": xg_ag,
                        "shots_avg": shots,
                        "possession_avg": poss,
                        "home_attack_strength": round(xg_for / 1.45, 3),
                        "home_defense_strength": round(xg_ag / 1.30, 3),
                        "away_attack_strength": round((xg_for * 0.88) / 1.25, 3),
                        "away_defense_strength": round((xg_ag * 1.12) / 1.35, 3),
                        "recent_form": form,
                    },
                )
            )
        return teams

    def fetch_matches(self, league_code: str, days_ahead: int = 7) -> list[RawMatch]:
        items = TEAMS_SEED.get(league_code, [])
        if len(items) < 2:
            return []

        rng = random.Random(f"seed-{league_code}-2026")
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        league_name = LEAGUE_NAMES.get(league_code, league_code)
        matches: list[RawMatch] = []

        # 1. Pertandingan historis selesai (untuk H2H, Form, dan Backtest)
        match_idx = 1
        for day_offset in range(-45, 0, 4):
            pair_indices = list(range(len(items)))
            rng.shuffle(pair_indices)
            for i in range(0, len(pair_indices) - 1, 2):
                home = items[pair_indices[i]]
                away = items[pair_indices[i + 1]]
                lam_h = max(0.5, home[4] * (away[5] / 1.2) * 1.1)
                lam_a = max(0.4, away[4] * (home[5] / 1.2) * 0.9)
                hs = min(5, int(round(rng.expovariate(1.0 / lam_h) * 0.65)))
                as_ = min(5, int(round(rng.expovariate(1.0 / lam_a) * 0.65)))
                m_date = now + timedelta(days=day_offset, hours=rng.choice([18, 20, 21]))
                matches.append(
                    RawMatch(
                        external_id=f"{league_code.lower()}-hist-{match_idx}",
                        league_code=league_code,
                        league_name=league_name,
                        match_date=m_date,
                        status="FINISHED",
                        home_team_ext_id=home[0],
                        away_team_ext_id=away[0],
                        home_score=hs,
                        away_score=as_,
                        venue=f"Stadion {home[1]}",
                        injuries_json=None,
                    )
                )
                match_idx += 1

        # 2. Pertandingan hari ini & hingga 7 hari ke depan
        upcoming_idx = 1
        for day_offset in range(0, days_ahead + 1, 2):
            pair_indices = list(range(len(items)))
            rng.shuffle(pair_indices)
            for i in range(0, len(pair_indices) - 1, 2):
                home = items[pair_indices[i]]
                away = items[pair_indices[i + 1]]
                m_date = now + timedelta(days=day_offset, hours=rng.choice([19, 20, 21]))
                if day_offset == 0 and m_date <= now:
                    m_date = now + timedelta(hours=3 + i)
                matches.append(
                    RawMatch(
                        external_id=f"{league_code.lower()}-up-{upcoming_idx}",
                        league_code=league_code,
                        league_name=league_name,
                        match_date=m_date,
                        status="SCHEDULED",
                        home_team_ext_id=home[0],
                        away_team_ext_id=away[0],
                        home_score=None,
                        away_score=None,
                        venue=f"Stadion {home[1]}",
                        injuries_json={
                            "home": [rng.choice(SAMPLE_INJURIES)],
                            "away": [rng.choice(SAMPLE_INJURIES)],
                        },
                    )
                )
                upcoming_idx += 1

        return matches
