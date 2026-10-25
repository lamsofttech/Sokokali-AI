import asyncio

import pytest

from app.integrations.sports.simulated import SimulatedSportsProvider
from app.services.prediction_engine import (
    InsufficientDataError,
    MatchNotFoundError,
    PredictionEngine,
    compute_elo,
    elo_probabilities,
    poisson_probability,
    predict_match,
    team_form,
)


def _engine(provider: SimulatedSportsProvider, **kwargs) -> PredictionEngine:
    return PredictionEngine(provider, model_version="test-1", **kwargs)


def test_poisson_probability_known_value() -> None:
    assert poisson_probability(0, 1.0) == pytest.approx(0.367879, rel=1e-5)


def test_poisson_rejects_negative_input() -> None:
    with pytest.raises(ValueError):
        poisson_probability(-1, 1.0)
    with pytest.raises(ValueError):
        predict_match(-0.1, 1.0)


def test_predict_match_sums_to_one_and_is_symmetric() -> None:
    result = predict_match(1.3, 1.3)
    assert result.home_win + result.draw + result.away_win == pytest.approx(1.0)
    assert result.home_win == pytest.approx(result.away_win)


def test_stronger_attack_is_favoured() -> None:
    result = predict_match(2.2, 0.8)
    assert result.home_win > result.draw
    assert result.home_win > result.away_win


def test_elo_probabilities_valid_for_extreme_gaps() -> None:
    for diff in (-1500, -400, 0, 400, 1500):
        p = elo_probabilities(1500 + diff, 1500)
        assert min(p.home_win, p.draw, p.away_win) >= 0
        assert p.home_win + p.draw + p.away_win == pytest.approx(1.0)


def test_elo_rewards_winners(provider: SimulatedSportsProvider) -> None:
    results = asyncio.run(provider.get_results())
    ratings = compute_elo(results)
    assert sum(ratings.values()) == pytest.approx(1500 * len(ratings))  # Elo is zero-sum


def test_team_form_length_and_alphabet(provider: SimulatedSportsProvider) -> None:
    results = asyncio.run(provider.get_results())
    form = team_form(results, "arsenal")
    assert len(form) == 5
    assert set(form) <= {"W", "D", "L"}


def test_prediction_output_contract(provider: SimulatedSportsProvider) -> None:
    fixture = asyncio.run(provider.get_fixtures())[0]
    prediction = asyncio.run(_engine(provider).predict(fixture.match_id))
    p = prediction.probabilities
    assert p.home_win + p.draw + p.away_win == pytest.approx(1.0, abs=1e-9)
    assert prediction.match_id == fixture.match_id
    assert prediction.model_version == "test-1"
    assert prediction.freshness.is_simulated is True
    assert prediction.expected_goals.home > 0 and prediction.expected_goals.away > 0
    assert any("SIMULATED" in factor for factor in prediction.key_factors)
    assert "not guaranteed" in prediction.disclaimer


def test_prediction_is_deterministic_for_same_seed() -> None:
    a = SimulatedSportsProvider(seed=7)
    b = SimulatedSportsProvider(seed=7)
    match_id = asyncio.run(a.get_fixtures())[0].match_id
    pa = asyncio.run(_engine(a).predict(match_id)).probabilities
    pb = asyncio.run(_engine(b).predict(match_id)).probabilities
    assert pa == pb


def test_unknown_match_raises(provider: SimulatedSportsProvider) -> None:
    with pytest.raises(MatchNotFoundError):
        asyncio.run(_engine(provider).predict("does-not-exist"))


def test_insufficient_history_raises(provider: SimulatedSportsProvider) -> None:
    fixture = asyncio.run(provider.get_fixtures())[0]
    with pytest.raises(InsufficientDataError):
        asyncio.run(_engine(provider, min_history_matches=10_000).predict(fixture.match_id))
