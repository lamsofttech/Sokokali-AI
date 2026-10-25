"""Football match prediction: independent Poisson goals blended with Elo.

Model (version set by ``Settings.prediction_model_version``):

1. Attack/defence strengths per team from historical goals, shrunk towards
   the league average so small samples do not produce extreme numbers.
2. Expected goals: ``league_home_mean * attack(home) * defence(away)`` and
   ``league_away_mean * attack(away) * defence(home)``.
3. Home/draw/away from an independent Poisson score matrix.
4. Elo ratings computed chronologically over the same history, converted to
   home/draw/away and blended with the Poisson output.

This is a transparent baseline, not a calibrated betting model. Backtesting
and calibration metrics arrive in Phase 3.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime

from app.integrations.sports.base import SportsDataProvider
from app.schemas.sports import (
    ExpectedGoals,
    Fixture,
    MatchResult,
    Prediction,
    Probabilities,
)


class MatchNotFoundError(Exception):
    pass


class InsufficientDataError(Exception):
    pass


@dataclass(frozen=True)
class MatchProbabilities:
    home_win: float
    draw: float
    away_win: float


def poisson_probability(goals: int, expected_goals: float) -> float:
    if goals < 0 or expected_goals < 0:
        raise ValueError("Goals and expected goals must be nonnegative")
    return math.exp(-expected_goals) * expected_goals**goals / math.factorial(goals)


def predict_match(home_xg: float, away_xg: float, max_goals: int = 10) -> MatchProbabilities:
    """Home/draw/away probabilities from two independent Poisson goal counts."""
    if home_xg < 0 or away_xg < 0 or max_goals < 1:
        raise ValueError("Expected goals must be nonnegative; max_goals must be positive")
    home = [poisson_probability(i, home_xg) for i in range(max_goals + 1)]
    away = [poisson_probability(i, away_xg) for i in range(max_goals + 1)]
    win = draw = loss = 0.0
    for i, p_home in enumerate(home):
        for j, p_away in enumerate(away):
            p = p_home * p_away
            if i > j:
                win += p
            elif i == j:
                draw += p
            else:
                loss += p
    total = win + draw + loss
    return MatchProbabilities(win / total, draw / total, loss / total)


def compute_elo(
    results: list[MatchResult],
    k_factor: float = 20.0,
    home_advantage: float = 60.0,
    initial: float = 1500.0,
) -> dict[str, float]:
    """Elo ratings with a goal-difference multiplier; ``results`` must be oldest first."""
    ratings: dict[str, float] = {}
    for r in results:
        home, away = r.home_team.team_id, r.away_team.team_id
        rh, ra = ratings.get(home, initial), ratings.get(away, initial)
        expected_home = 1.0 / (1.0 + 10 ** (-(rh + home_advantage - ra) / 400))
        actual_home = 1.0 if r.home_goals > r.away_goals else 0.5 if r.home_goals == r.away_goals else 0.0
        margin = math.log(abs(r.home_goals - r.away_goals) + 1) + 1
        delta = k_factor * margin * (actual_home - expected_home)
        ratings[home] = rh + delta
        ratings[away] = ra - delta
    return ratings


def elo_probabilities(home_rating: float, away_rating: float, home_advantage: float = 60.0) -> MatchProbabilities:
    """Convert an Elo gap to home/draw/away; draws are likeliest when teams are level."""
    diff = home_rating + home_advantage - away_rating
    expected_home = 1.0 / (1.0 + 10 ** (-diff / 400))
    draw = min(0.28 * math.exp(-((diff / 400) ** 2)), 2 * min(expected_home, 1 - expected_home))
    return MatchProbabilities(expected_home - draw / 2, draw, 1 - expected_home - draw / 2)


def team_form(results: list[MatchResult], team_id: str, last: int = 5) -> str:
    """Most recent results first, e.g. ``"WWDLW"``."""
    form = []
    for r in reversed(results):
        if team_id not in (r.home_team.team_id, r.away_team.team_id):
            continue
        scored, conceded = (
            (r.home_goals, r.away_goals) if r.home_team.team_id == team_id else (r.away_goals, r.home_goals)
        )
        form.append("W" if scored > conceded else "D" if scored == conceded else "L")
        if len(form) == last:
            break
    return "".join(form)


@dataclass(frozen=True)
class _Strengths:
    home_mean: float
    away_mean: float
    attack: dict[str, float]
    defence: dict[str, float]


def _team_strengths(results: list[MatchResult], shrinkage_games: float = 5.0) -> _Strengths:
    n = len(results)
    home_mean = sum(r.home_goals for r in results) / n
    away_mean = sum(r.away_goals for r in results) / n
    goals_per_team_game = (home_mean + away_mean) / 2 or 1e-9

    scored: dict[str, int] = {}
    conceded: dict[str, int] = {}
    played: dict[str, int] = {}
    for r in results:
        for team, gf, ga in (
            (r.home_team.team_id, r.home_goals, r.away_goals),
            (r.away_team.team_id, r.away_goals, r.home_goals),
        ):
            scored[team] = scored.get(team, 0) + gf
            conceded[team] = conceded.get(team, 0) + ga
            played[team] = played.get(team, 0) + 1

    def shrink(total: int, games: int) -> float:
        raw = total / games / goals_per_team_game
        return (games * raw + shrinkage_games * 1.0) / (games + shrinkage_games)

    return _Strengths(
        home_mean=home_mean,
        away_mean=away_mean,
        attack={t: shrink(scored[t], played[t]) for t in played},
        defence={t: shrink(conceded[t], played[t]) for t in played},
    )


class PredictionEngine:
    def __init__(
        self,
        provider: SportsDataProvider,
        model_version: str,
        poisson_weight: float = 0.7,
        min_history_matches: int = 10,
    ) -> None:
        self.provider = provider
        self.model_version = model_version
        self.poisson_weight = poisson_weight
        self.min_history_matches = min_history_matches

    async def predict(self, match_id: str) -> Prediction:
        fixture = await self.provider.get_fixture(match_id)
        if fixture is None:
            raise MatchNotFoundError(match_id)
        return await self.predict_fixture(fixture)

    async def predict_fixture(self, fixture: Fixture) -> Prediction:
        history = await self.provider.get_results(competition=fixture.competition)
        home_id, away_id = fixture.home_team.team_id, fixture.away_team.team_id
        if len(history) < self.min_history_matches:
            raise InsufficientDataError(f"Only {len(history)} historical matches for {fixture.competition}")
        strengths = _team_strengths(history)
        if home_id not in strengths.attack or away_id not in strengths.attack:
            raise InsufficientDataError("No historical matches for one of the teams")

        home_xg = strengths.home_mean * strengths.attack[home_id] * strengths.defence[away_id]
        away_xg = strengths.away_mean * strengths.attack[away_id] * strengths.defence[home_id]
        poisson = predict_match(home_xg, away_xg)

        elo = compute_elo(history)
        elo_probs = elo_probabilities(elo[home_id], elo[away_id])

        w = self.poisson_weight
        blended = [
            w * p + (1 - w) * e
            for p, e in zip(
                (poisson.home_win, poisson.draw, poisson.away_win),
                (elo_probs.home_win, elo_probs.draw, elo_probs.away_win),
                strict=True,
            )
        ]
        total = sum(blended)
        home_p, draw_p, away_p = (round(p / total, 4) for p in blended)
        draw_p = round(1 - home_p - away_p, 4)  # make the three values sum to exactly 1

        home_name, away_name = fixture.home_team.name, fixture.away_team.name
        home_form, away_form = team_form(history, home_id), team_form(history, away_id)
        key_factors = [
            f"Expected goals: {home_name} {home_xg:.2f} vs {away_name} {away_xg:.2f}",
            f"Elo rating: {home_name} {elo[home_id]:.0f} vs {away_name} {elo[away_id]:.0f} "
            "(home advantage +60 applied)",
            f"Recent form (latest first): {home_name} {home_form or 'n/a'}, {away_name} {away_form or 'n/a'}",
            f"Based on {len(history)} historical matches in {fixture.competition}",
        ]
        if self.provider.is_simulated:
            key_factors.append("All inputs are SIMULATED data, not real match statistics")

        return Prediction(
            match_id=fixture.match_id,
            competition=fixture.competition,
            home_team=home_name,
            away_team=away_name,
            kickoff=fixture.kickoff,
            predicted_at=datetime.now(UTC),
            freshness=self.provider.freshness(),
            probabilities=Probabilities(home_win=home_p, draw=draw_p, away_win=away_p),
            expected_goals=ExpectedGoals(home=round(home_xg, 2), away=round(away_xg, 2)),
            model_version=self.model_version,
            key_factors=key_factors,
        )
