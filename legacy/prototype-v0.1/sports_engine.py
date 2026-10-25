from dataclasses import dataclass
from math import exp, factorial


@dataclass(frozen=True)
class MatchPrediction:
    home_win: float
    draw: float
    away_win: float


def poisson_probability(goals: int, expected_goals: float) -> float:
    if goals < 0 or expected_goals < 0:
        raise ValueError("Goals and expected goals must be nonnegative")
    return exp(-expected_goals) * expected_goals**goals / factorial(goals)


def predict_match(home_xg: float, away_xg: float, max_goals: int = 15) -> MatchPrediction:
    """Illustrative independent-Poisson model; not a calibrated betting forecast."""
    if home_xg < 0 or away_xg < 0 or max_goals < 1:
        raise ValueError("Expected goals must be nonnegative; max_goals must be positive")
    home = [poisson_probability(i, home_xg) for i in range(max_goals + 1)]
    away = [poisson_probability(i, away_xg) for i in range(max_goals + 1)]
    win = draw = loss = 0.0
    for i, p_home in enumerate(home):
        for j, p_away in enumerate(away):
            probability = p_home * p_away
            if i > j:
                win += probability
            elif i == j:
                draw += probability
            else:
                loss += probability
    total = win + draw + loss
    return MatchPrediction(win / total, draw / total, loss / total)
