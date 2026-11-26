import math
from dataclasses import dataclass


@dataclass
class PoissonPredictionResult:
    prob_home: float
    prob_draw: float
    prob_away: float
    prob_over_25: float
    prob_under_25: float
    prob_btts_yes: float
    prob_btts_no: float
    predicted_home_score: int
    predicted_away_score: int
    score_matrix: list[list[float]]


def _tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Faktor koreksi Dixon-Coles untuk skor rendah (0-0, 1-0, 0-1, 1-1)."""
    if x == 0 and y == 0:
        return max(0.0, 1.0 - (lam * mu * rho))
    if x == 0 and y == 1:
        return max(0.0, 1.0 + (lam * rho))
    if x == 1 and y == 0:
        return max(0.0, 1.0 + (mu * rho))
    if x == 1 and y == 1:
        return max(0.0, 1.0 - rho)
    return 1.0


def _poisson_pmf(k: int, lam: float) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def dixon_coles_probs(
    lambda_home: float,
    lambda_away: float,
    rho: float = -0.10,
    max_goals: int = 8,
) -> PoissonPredictionResult:
    """Menghitung distribusi probabilitas skor, 1X2, Over/Under 2.5, dan BTTS."""
    lam = max(0.15, min(4.5, lambda_home))
    mu = max(0.15, min(4.5, lambda_away))

    matrix: list[list[float]] = []
    total_mass = 0.0

    for i in range(max_goals + 1):
        row = []
        p_i = _poisson_pmf(i, lam)
        for j in range(max_goals + 1):
            p_j = _poisson_pmf(j, mu)
            val = p_i * p_j * _tau(i, j, lam, mu, rho)
            row.append(val)
            total_mass += val
        matrix.append(row)

    # Normalisasi agar jumlah probabilitas matriks = 1.0
    prob_home = 0.0
    prob_draw = 0.0
    prob_away = 0.0
    prob_over_25 = 0.0
    prob_btts_yes = 0.0
    best_score = (0, 0)
    best_p = -1.0

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = matrix[i][j] / total_mass if total_mass > 0 else 0.0
            matrix[i][j] = p
            if i > j:
                prob_home += p
            elif i == j:
                prob_draw += p
            else:
                prob_away += p
            if (i + j) > 2:
                prob_over_25 += p
            if i >= 1 and j >= 1:
                prob_btts_yes += p
            if p > best_p:
                best_p = p
                best_score = (i, j)

    return PoissonPredictionResult(
        prob_home=round(prob_home, 4),
        prob_draw=round(prob_draw, 4),
        prob_away=round(prob_away, 4),
        prob_over_25=round(prob_over_25, 4),
        prob_under_25=round(1.0 - prob_over_25, 4),
        prob_btts_yes=round(prob_btts_yes, 4),
        prob_btts_no=round(1.0 - prob_btts_yes, 4),
        predicted_home_score=best_score[0],
        predicted_away_score=best_score[1],
        score_matrix=matrix,
    )
