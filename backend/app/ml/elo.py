import math


def expected_elo_score(elo_home: float, elo_away: float, home_advantage: float = 65.0) -> float:
    """Menghitung ekspektasi skor (0..1) untuk tim kandang berdasarkan selisih rating Elo."""
    diff = (elo_home + home_advantage) - elo_away
    return 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))


def update_elo(
    elo_home: float,
    elo_away: float,
    home_goals: int,
    away_goals: int,
    k_factor: float = 24.0,
    home_advantage: float = 65.0,
) -> tuple[float, float]:
    """Memperbarui rating Elo kandang dan tandang setelah pertandingan selesai."""
    exp_home = expected_elo_score(elo_home, elo_away, home_advantage=home_advantage)
    if home_goals > away_goals:
        actual_home = 1.0
    elif home_goals == away_goals:
        actual_home = 0.5
    else:
        actual_home = 0.0

    goal_diff = abs(home_goals - away_goals)
    margin_mult = math.log(goal_diff + 1.0) * (2.2 / ((abs(elo_home - elo_away) * 0.001) + 2.2)) if goal_diff > 1 else 1.0

    delta = k_factor * margin_mult * (actual_home - exp_home)
    return round(elo_home + delta, 2), round(elo_away - delta, 2)
