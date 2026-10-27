"""Football match prediction: independent Poisson goals blended with Elo.

Model (version set by ``Settings.prediction_model_version``):

1. Attack/defence strengths per team from historical goals, shrunk towards
   the league average so small samples do not produce extreme numbers.
2. Expected goals: ``league_home_mean * attack(home) * defence(away)`` and
   ``league_away_mean * attack(away) * defence(home)``.
3. Home/draw/away from an independent Poisson score matrix.
4. Elo ratings computed chronologically over the same history, converted to
   home/draw/away and blended with the Poisson output.

This is a transparent baseline, not a calibrated betting model. Its
walk-forward log loss, Brier score and calibration are measured in
``app.services.backtest``.
"""

import asyncio
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.background import spawn
from app.integrations.sports.base import SportsDataProvider
from app.schemas.sports import (
    ExpectedGoals,
    Fixture,
    MatchResult,
    Prediction,
    Probabilities,
)


if TYPE_CHECKING:
    from app.services.backtest import BacktestReport


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


DEFAULT_ELO = 1500.0
ELO_HOME_ADVANTAGE = 60.0


@dataclass(frozen=True)
class FittedModel:
    """Everything the model learns from a block of finished matches."""

    strengths: _Strengths
    elo: dict[str, float]
    n_matches: int


@dataclass(frozen=True)
class Estimate:
    poisson: MatchProbabilities
    elo: MatchProbabilities
    blended: MatchProbabilities
    home_xg: float
    away_xg: float
    home_elo: float
    away_elo: float
    known_home: bool
    known_away: bool


def fit_model(results: list[MatchResult]) -> FittedModel:
    """Fit on finished matches, oldest first. Callers must pass only matches before the one being predicted."""
    if not results:
        raise InsufficientDataError("No historical matches")
    return FittedModel(_team_strengths(results), compute_elo(results), len(results))


def estimate(model: FittedModel, home_id: str, away_id: str, poisson_weight: float) -> Estimate:
    """Probabilities for one match. Teams without history are treated as league-average (attack = defence = 1)."""
    s = model.strengths
    home_xg = s.home_mean * s.attack.get(home_id, 1.0) * s.defence.get(away_id, 1.0)
    away_xg = s.away_mean * s.attack.get(away_id, 1.0) * s.defence.get(home_id, 1.0)
    poisson = predict_match(home_xg, away_xg)
    home_elo, away_elo = model.elo.get(home_id, DEFAULT_ELO), model.elo.get(away_id, DEFAULT_ELO)
    elo = elo_probabilities(home_elo, away_elo, ELO_HOME_ADVANTAGE)
    w = poisson_weight
    raw = [
        w * p + (1 - w) * e
        for p, e in zip(
            (poisson.home_win, poisson.draw, poisson.away_win), (elo.home_win, elo.draw, elo.away_win), strict=True
        )
    ]
    total = sum(raw)
    blended = MatchProbabilities(raw[0] / total, raw[1] / total, raw[2] / total)
    return Estimate(
        poisson, elo, blended, home_xg, away_xg, home_elo, away_elo, home_id in s.attack, away_id in s.attack
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
        # Fitted models and backtests are reused until the provider's data changes (keys include data_as_of).
        self._models: dict[tuple[str, datetime, int], FittedModel] = {}
        self._evaluations: dict[tuple[datetime, int, int], "BacktestReport"] = {}
        # Called (in the background) with every prediction, e.g. to store it with its model version.
        self.on_prediction: Callable[[Prediction], Awaitable[None]] | None = None

    async def evaluate(self, warmup_matches: int = 20, refit_every: int = 1) -> "BacktestReport":
        """Walk-forward backtest over all finished matches the provider has."""
        from app.services.backtest import backtest  # imported here: backtest builds on this module

        key = (self.provider.data_as_of(), warmup_matches, refit_every)
        report = self._evaluations.get(key)
        if report is None:
            results = await self.provider.get_results()
            report = await asyncio.to_thread(
                backtest, results, self.poisson_weight, warmup_matches, refit_every
            )  # CPU-bound: keep it off the event loop
            self._evaluations = {key: report}
        return report

    async def predict(self, match_id: str) -> Prediction:
        fixture = await self.provider.get_fixture(match_id)
        if fixture is None:
            raise MatchNotFoundError(match_id)
        return await self.predict_fixture(fixture)

    def _model_for(self, competition: str, history: list[MatchResult]) -> FittedModel:
        key = (competition, self.provider.data_as_of(), len(history))
        model = self._models.get(key)
        if model is None:
            if len(self._models) > 32:
                self._models.clear()
            model = self._models[key] = fit_model(history)
        return model

    async def predict_fixture(self, fixture: Fixture) -> Prediction:
        history = await self.provider.get_results(competition=fixture.competition)
        if len(history) < self.min_history_matches:
            raise InsufficientDataError(f"Only {len(history)} historical matches for {fixture.competition}")
        home_id, away_id = fixture.home_team.team_id, fixture.away_team.team_id
        est = estimate(self._model_for(fixture.competition, history), home_id, away_id, self.poisson_weight)

        home_p, away_p = round(est.blended.home_win, 4), round(est.blended.away_win, 4)
        draw_p = round(1 - home_p - away_p, 4)  # make the three values sum to exactly 1

        home_name, away_name = fixture.home_team.name, fixture.away_team.name
        home_form, away_form = team_form(history, home_id), team_form(history, away_id)
        key_factors = [
            f"Expected goals: {home_name} {est.home_xg:.2f} vs {away_name} {est.away_xg:.2f}",
            f"Elo rating: {home_name} {est.home_elo:.0f} vs {away_name} {est.away_elo:.0f} "
            f"(home advantage +{ELO_HOME_ADVANTAGE:.0f} applied)",
            f"Recent form (latest first): {home_name} {home_form or 'n/a'}, {away_name} {away_form or 'n/a'}",
            f"Based on {len(history)} historical matches in {fixture.competition}",
        ]
        unknown = [name for name, known in ((home_name, est.known_home), (away_name, est.known_away)) if not known]
        if unknown:
            key_factors.append(f"No match history for {', '.join(unknown)}: rated as league average")
        if self.provider.is_simulated:
            key_factors.append("All inputs are SIMULATED data, not real match statistics")

        prediction = Prediction(
            match_id=fixture.match_id,
            competition=fixture.competition,
            home_team=home_name,
            away_team=away_name,
            kickoff=fixture.kickoff,
            predicted_at=datetime.now(UTC),
            freshness=self.provider.freshness(),
            probabilities=Probabilities(home_win=home_p, draw=draw_p, away_win=away_p),
            expected_goals=ExpectedGoals(home=round(est.home_xg, 2), away=round(est.away_xg, 2)),
            model_version=self.model_version,
            key_factors=key_factors,
        )
        if self.on_prediction is not None:
            spawn(self.on_prediction(prediction), "save_prediction")
        return prediction
