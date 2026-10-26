"""Walk-forward backtesting of the football prediction model.

For every finished match after a warm-up period, the model is fitted only on
matches that kicked off *before* it (no future data leaks in), predicts the
match, and the prediction is scored against the real result. Four models are
compared on exactly the same matches:

- ``baseline``: home/draw/away frequencies seen so far (the bar to beat)
- ``poisson``: expected-goals Poisson model alone
- ``elo``: Elo ratings alone
- ``blend``: the production model (``poisson_weight`` x Poisson + rest x Elo)

Metrics (lower is better unless noted):

- log loss: -ln(probability given to what actually happened)
- Brier score: squared error summed over the three outcomes (0 to 2)
- accuracy (higher is better): how often the most likely outcome happened
- calibration: predicted probabilities grouped into bins vs. how often those
  outcomes really happened; a well-calibrated model has the two close.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field

from app.schemas.sports import MatchResult
from app.services.prediction_engine import MatchProbabilities, estimate, fit_model

MODELS = ("baseline", "poisson", "elo", "blend")
_EPS = 1e-15


@dataclass
class _Accumulator:
    n: int = 0
    log_loss: float = 0.0
    brier: float = 0.0
    correct: int = 0
    # bin index -> [sum of predicted probability, outcomes that happened, count]
    bins: dict[int, list[float]] = field(default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))

    def add(self, probs: tuple[float, float, float], outcome: int, n_bins: int) -> None:
        self.n += 1
        self.log_loss -= math.log(max(probs[outcome], _EPS))
        self.brier += sum((p - (1.0 if i == outcome else 0.0)) ** 2 for i, p in enumerate(probs))
        self.correct += int(max(range(3), key=lambda i: probs[i]) == outcome)
        for i, p in enumerate(probs):
            b = self.bins[min(int(p * n_bins), n_bins - 1)]
            b[0] += p
            b[1] += 1.0 if i == outcome else 0.0
            b[2] += 1


@dataclass(frozen=True)
class CalibrationBin:
    lower: float
    upper: float
    mean_predicted: float
    observed_frequency: float
    count: int


@dataclass(frozen=True)
class ModelMetrics:
    model: str
    matches: int
    log_loss: float
    brier_score: float
    accuracy: float
    calibration: list[CalibrationBin]


@dataclass(frozen=True)
class BacktestReport:
    competitions: list[str]
    matches_evaluated: int
    warmup_matches: int
    poisson_weight: float
    outcome_frequencies: dict[str, float]
    metrics: list[ModelMetrics]

    def best_model(self) -> str:
        return min(self.metrics, key=lambda m: m.log_loss).model if self.metrics else ""


def _outcome(r: MatchResult) -> int:
    return 0 if r.home_goals > r.away_goals else 1 if r.home_goals == r.away_goals else 2


def _as_tuple(p: MatchProbabilities) -> tuple[float, float, float]:
    return (p.home_win, p.draw, p.away_win)


def backtest(
    results: list[MatchResult],
    poisson_weight: float = 0.7,
    warmup_matches: int = 20,
    refit_every: int = 1,
    n_bins: int = 10,
) -> BacktestReport:
    """Evaluate the models walk-forward, separately within each competition, then pool the scores."""
    by_competition: dict[str, list[MatchResult]] = defaultdict(list)
    for r in sorted(results, key=lambda r: r.kickoff):
        by_competition[r.competition].append(r)

    acc = {m: _Accumulator() for m in MODELS}
    outcome_counts = [0, 0, 0]
    for matches in by_competition.values():
        model = None
        fitted_on = -1
        for i in range(warmup_matches, len(matches)):
            target = matches[i]
            # Only matches strictly before this kickoff may be used for training.
            train_end = i
            while train_end > 0 and matches[train_end - 1].kickoff >= target.kickoff:
                train_end -= 1
            if train_end < warmup_matches:
                continue
            if model is None or train_end - fitted_on >= refit_every:
                model = fit_model(matches[:train_end])
                fitted_on = train_end
            train = matches[:train_end]
            counts = [0, 0, 0]
            for r in train:
                counts[_outcome(r)] += 1
            baseline = (counts[0] / len(train), counts[1] / len(train), counts[2] / len(train))

            est = estimate(model, target.home_team.team_id, target.away_team.team_id, poisson_weight)
            outcome = _outcome(target)
            outcome_counts[outcome] += 1
            for name, probs in (
                ("baseline", baseline),
                ("poisson", _as_tuple(est.poisson)),
                ("elo", _as_tuple(est.elo)),
                ("blend", _as_tuple(est.blended)),
            ):
                acc[name].add(probs, outcome, n_bins)

    evaluated = acc["blend"].n
    metrics = []
    for name in MODELS:
        a = acc[name]
        if not a.n:
            continue
        calibration = [
            CalibrationBin(
                lower=i / n_bins,
                upper=(i + 1) / n_bins,
                mean_predicted=round(b[0] / b[2], 4),
                observed_frequency=round(b[1] / b[2], 4),
                count=int(b[2]),
            )
            for i, b in sorted(a.bins.items())
        ]
        metrics.append(
            ModelMetrics(
                model=name,
                matches=a.n,
                log_loss=round(a.log_loss / a.n, 4),
                brier_score=round(a.brier / a.n, 4),
                accuracy=round(a.correct / a.n, 4),
                calibration=calibration,
            )
        )
    total = sum(outcome_counts) or 1
    return BacktestReport(
        competitions=sorted(by_competition),
        matches_evaluated=evaluated,
        warmup_matches=warmup_matches,
        poisson_weight=poisson_weight,
        outcome_frequencies={
            "home_win": round(outcome_counts[0] / total, 4),
            "draw": round(outcome_counts[1] / total, 4),
            "away_win": round(outcome_counts[2] / total, 4),
        },
        metrics=metrics,
    )
