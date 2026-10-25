"""Tests for the rate limiter, conversation memory and simulated provider."""

import asyncio

from app.core.rate_limit import SlidingWindowRateLimiter
from app.integrations.sports.simulated import SimulatedSportsProvider
from app.schemas.chat import Intent
from app.services.conversation_memory import ConversationMemory, Turn
from app.services.sports_engine import SportsService


def test_rate_limiter_window_expires() -> None:
    limiter = SlidingWindowRateLimiter(limit=2, window_seconds=10)
    assert limiter.allow("ip", now=0)
    assert limiter.allow("ip", now=1)
    assert not limiter.allow("ip", now=2)
    assert limiter.allow("other-ip", now=2)
    assert limiter.allow("ip", now=11)


def _turn(team_ids: tuple[str, ...] = ()) -> Turn:
    return Turn("msg", "reply", Intent.UNKNOWN, team_ids, 0.0)


def test_memory_is_bounded() -> None:
    memory = ConversationMemory(max_turns=3)
    for _ in range(5):
        memory.add("v", _turn())
    assert len(memory.history("v")) == 3


def test_memory_last_team_ids() -> None:
    memory = ConversationMemory()
    memory.add("v", _turn(("arsenal", "chelsea")))
    memory.add("v", _turn())
    assert memory.last_team_ids("v") == ("arsenal", "chelsea")


def test_memory_evicts_oldest_viewer_when_full() -> None:
    memory = ConversationMemory(max_viewers=2)
    for viewer in ("a", "b", "c"):
        memory.add(viewer, _turn())
    assert len(memory) == 2
    assert memory.history("a") == []


def test_simulated_provider_data_integrity(provider: SimulatedSportsProvider) -> None:
    results = asyncio.run(provider.get_results())
    fixtures = asyncio.run(provider.get_fixtures())
    assert len(results) == 2 * 8 * 7  # two leagues, double round-robin of 8 teams
    assert all(r.kickoff < provider.data_as_of() for r in results)
    assert all(f.kickoff > provider.data_as_of() for f in fixtures)
    assert len({r.match_id for r in results} | {f.match_id for f in fixtures}) == len(results) + len(fixtures)


def test_find_teams_by_alias(provider: SimulatedSportsProvider) -> None:
    sports = SportsService(provider)
    teams = asyncio.run(sports.find_teams("K'Ogalo vs Ingwe, then Man City and Spurs"))
    assert [t.team_id for t in teams] == ["gor-mahia", "afc-leopards", "man-city", "tottenham"]


def test_find_teams_ignores_partial_words(provider: SimulatedSportsProvider) -> None:
    sports = SportsService(provider)
    assert asyncio.run(sports.find_teams("I love the city of Gorgeous Nairobi")) == []
