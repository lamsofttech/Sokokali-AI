"""Audience engagement: community milestones, free trivia, prediction polls, recognition.

Fairness rules (Module E):
- Everything that earns points or recognition is free: commenting, answering
  trivia, voting in polls.
- Gifts only trigger cosmetic effects (confetti, a thank-you). They never give
  points, priority for answers, or anything to do with predictions or betting.
- Milestones are community goals reached together; their rewards are cosmetic
  (avatar outfits, studio backgrounds).
"""

import random
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.live import LiveEvent, LiveEventKind

Metric = Literal["likes", "viewers", "comments"]


@dataclass(frozen=True)
class Milestone:
    id: str
    metric: Metric
    target: int
    reward: str  # "outfit:<name>", "background:<name>" or "" for a celebration only
    label: str


MILESTONES = [
    Milestone("viewers-10", "viewers", 10, "", "10 viewers in the stadium"),
    Milestone("likes-100", "likes", 100, "background:floodlights", "100 likes: floodlights on"),
    Milestone("comments-50", "comments", 50, "", "50 comments"),
    Milestone("viewers-25", "viewers", 25, "background:derby_night", "25 viewers: derby night"),
    Milestone("likes-500", "likes", 500, "outfit:away", "500 likes: away jersey"),
    Milestone("likes-2000", "likes", 2000, "outfit:gold", "2,000 likes: golden jersey"),
]


@dataclass(frozen=True)
class TriviaQuestion:
    question_en: str
    question_sw: str
    options: tuple[str, str, str, str]
    answer: int  # index into options


TRIVIA = [
    TriviaQuestion("Which country won the 2022 FIFA World Cup?", "Nchi gani ilishinda Kombe la Dunia la FIFA 2022?",
                   ("France", "Argentina", "Brazil", "Croatia"), 1),
    TriviaQuestion("How many players does each team have on the pitch?", "Kila timu ina wachezaji wangapi uwanjani?",
                   ("9", "10", "11", "12"), 2),
    TriviaQuestion("Which Kenyan club is nicknamed K'Ogalo?", "Klabu gani ya Kenya inaitwa K'Ogalo?",
                   ("AFC Leopards", "Tusker FC", "Gor Mahia", "Bandari FC"), 2),
    TriviaQuestion("What is AFC Leopards' nickname?", "AFC Leopards inajulikana kwa jina gani la utani?",
                   ("Ingwe", "Simba", "Chui Mweusi", "Bankers"), 0),
    TriviaQuestion("How long is a standard football match, without stoppage time?",
                   "Mechi ya kawaida ya soka huchukua dakika ngapi, bila muda wa nyongeza?",
                   ("80 minutes", "90 minutes", "100 minutes", "120 minutes"), 1),
    TriviaQuestion("Which country hosted the 2010 FIFA World Cup?", "Nchi gani iliandaa Kombe la Dunia la FIFA 2010?",
                   ("Nigeria", "Egypt", "South Africa", "Morocco"), 2),
    TriviaQuestion("Harambee Stars is the national team of which country?",
                   "Harambee Stars ni timu ya taifa ya nchi gani?", ("Uganda", "Kenya", "Tanzania", "Ethiopia"), 1),
    TriviaQuestion("Which club is nicknamed 'The Gunners'?", "Klabu gani inaitwa 'The Gunners'?",
                   ("Chelsea", "Liverpool", "Arsenal", "Tottenham"), 2),
    TriviaQuestion("What is the currency code for the Kenyan shilling?", "Msimbo wa sarafu ya shilingi ya Kenya ni upi?",
                   ("KSH", "KES", "KEN", "KSS"), 1),
    TriviaQuestion("How many points does a team get for a league win?", "Timu hupata pointi ngapi kwa ushindi kwenye ligi?",
                   ("1", "2", "3", "4"), 2),
    TriviaQuestion("How many goals by one player make a hat-trick?", "Hat-trick ni mabao mangapi ya mchezaji mmoja?",
                   ("2", "3", "4", "5"), 1),
]
LETTERS = ("A", "B", "C", "D")
ANSWER_RE = re.compile(r"^(?:jibu(?: ni)?\s*|answer\s*:?\s*)?([abcd])[!.]?$")
POLL_OPTIONS = {"1": "home", "x": "draw", "2": "away"}

POINTS_TRIVIA_FIRST = 10
POINTS_TRIVIA_CORRECT = 5
POINTS_POLL_VOTE = 2
POINTS_COMMENT = 1  # at most once a minute per viewer


class GameUpdate(BaseModel):
    kind: Literal["milestone", "gift", "follow", "trivia_correct", "poll_vote", "trivia_closed", "poll_closed"]
    viewer_name: str | None = None
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class TriviaStatus(BaseModel):
    question_en: str
    question_sw: str
    options: list[str]
    closes_at: datetime
    answers: int
    winners: list[str]


class PollStatus(BaseModel):
    match_id: str
    home_team: str
    away_team: str
    closes_at: datetime
    votes: dict[str, int]


class MilestoneStatus(BaseModel):
    id: str
    label: str
    metric: Metric
    target: int
    current: int
    reached: bool


class LeaderboardEntry(BaseModel):
    viewer_name: str
    points: int


class GamificationStatus(BaseModel):
    totals: dict[str, int]
    milestones: list[MilestoneStatus]
    outfit: str
    background: str
    trivia: TriviaStatus | None
    poll: PollStatus | None
    leaderboard: list[LeaderboardEntry]
    last_poll_result: dict[str, Any] | None
    rules: str = "Points come only from free participation (comments, trivia, polls). Gifts are cosmetic only."


@dataclass
class _Trivia:
    question: TriviaQuestion
    closes_at: float
    closes_at_wall: datetime
    answered: set[str] = field(default_factory=set)
    winners: list[str] = field(default_factory=list)


@dataclass
class _Poll:
    match_id: str
    home: str
    away: str
    closes_at: float
    closes_at_wall: datetime
    votes: dict[str, str] = field(default_factory=dict)


class GamificationEngine:
    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self.totals: Counter[str] = Counter()
        self._viewers: set[str] = set()
        self._names: dict[str, str] = {}
        self.points: Counter[str] = Counter()
        self._last_comment_point: dict[str, float] = {}
        self.reached: set[str] = set()
        self.outfit = "home"
        self.background = "studio"
        self.trivia: _Trivia | None = None
        self.poll: _Poll | None = None
        self.last_poll_result: dict[str, Any] | None = None
        self._trivia_order = list(range(len(TRIVIA)))
        self._rng.shuffle(self._trivia_order)
        self._trivia_index = 0

    # -- events ---------------------------------------------------------------

    def process(self, event: LiveEvent, now: float) -> list[GameUpdate]:
        key = f"{event.platform}:{event.viewer_id}"
        self._names[key] = event.viewer_name
        updates: list[GameUpdate] = []
        if key not in self._viewers:
            self._viewers.add(key)
            self.totals["viewers"] = len(self._viewers)

        if event.kind == LiveEventKind.LIKE:
            self.totals["likes"] += event.count
        elif event.kind == LiveEventKind.GIFT:
            self.totals["gifts"] += event.count
            updates.append(
                GameUpdate(
                    kind="gift",
                    viewer_name=event.viewer_name,
                    message=f"Asante {event.viewer_name} for the {event.gift_name or 'gift'}!",
                    data={"effect": "confetti", "gift_name": event.gift_name},
                )
            )
        elif event.kind == LiveEventKind.FOLLOW:
            self.totals["follows"] += 1
            updates.append(GameUpdate(kind="follow", viewer_name=event.viewer_name, message=f"Karibu {event.viewer_name}!"))
        elif event.kind == LiveEventKind.SHARE:
            self.totals["shares"] += 1
        elif event.kind == LiveEventKind.COMMENT:
            self.totals["comments"] += 1
            if now - self._last_comment_point.get(key, -1e9) >= 60:
                self._last_comment_point[key] = now
                self.points[key] += POINTS_COMMENT
            updates += self._answer(key, event.viewer_name, (event.text or "").strip().lower(), now)

        updates += self._check_milestones()
        return updates

    def _answer(self, key: str, name: str, text: str, now: float) -> list[GameUpdate]:
        updates: list[GameUpdate] = []
        trivia = self.trivia
        match = ANSWER_RE.match(text)
        if trivia and now < trivia.closes_at and match and key not in trivia.answered:
            trivia.answered.add(key)
            if LETTERS.index(match.group(1).upper()) == trivia.question.answer:
                first = not trivia.winners
                self.points[key] += POINTS_TRIVIA_FIRST if first else POINTS_TRIVIA_CORRECT
                trivia.winners.append(name)
                updates.append(
                    GameUpdate(kind="trivia_correct", viewer_name=name, message=f"{name} got it right!", data={"first": first})
                )
        poll = self.poll
        if poll and now < poll.closes_at and key not in poll.votes:
            option = POLL_OPTIONS.get(text)
            if option is None and text in (poll.home.lower(), poll.away.lower()):
                option = "home" if text == poll.home.lower() else "away"
            if option:
                poll.votes[key] = option
                self.points[key] += POINTS_POLL_VOTE
                updates.append(GameUpdate(kind="poll_vote", viewer_name=name, message=f"{name} voted", data={"option": option}))
        return updates

    def _metric(self, metric: Metric) -> int:
        return self.totals[metric]

    def _check_milestones(self) -> list[GameUpdate]:
        updates = []
        for m in MILESTONES:
            if m.id in self.reached or self._metric(m.metric) < m.target:
                continue
            self.reached.add(m.id)
            kind, _, value = m.reward.partition(":")
            if kind == "outfit":
                self.outfit = value
            elif kind == "background":
                self.background = value
            updates.append(
                GameUpdate(
                    kind="milestone",
                    message=f"Community milestone: {m.label}! Asanteni wadau!",
                    data={"id": m.id, "outfit": self.outfit, "background": self.background, "effect": "celebration"},
                )
            )
        return updates

    # -- trivia and polls ---------------------------------------------------

    def start_trivia(self, now: float, duration_seconds: float) -> TriviaQuestion:
        question = TRIVIA[self._trivia_order[self._trivia_index % len(TRIVIA)]]
        self._trivia_index += 1
        self.trivia = _Trivia(question, now + duration_seconds, _wall(duration_seconds))
        return question

    def close_trivia(self) -> GameUpdate | None:
        trivia, self.trivia = self.trivia, None
        if trivia is None:
            return None
        q = trivia.question
        answer = f"{LETTERS[q.answer]}) {q.options[q.answer]}"
        winners = trivia.winners[:3]
        return GameUpdate(
            kind="trivia_closed",
            message=f"The answer was {answer}. "
            + (f"Well done {', '.join(winners)}!" if winners else "Nobody got it this time!"),
            data={"answer": answer, "winners": winners, "answers": len(trivia.answered)},
        )

    def start_poll(self, match_id: str, home: str, away: str, now: float, duration_seconds: float) -> None:
        self.poll = _Poll(match_id, home, away, now + duration_seconds, _wall(duration_seconds))

    def close_poll(self) -> GameUpdate | None:
        poll, self.poll = self.poll, None
        if poll is None:
            return None
        tally = Counter(poll.votes.values())
        total = sum(tally.values())
        result = {
            "match_id": poll.match_id,
            "home_team": poll.home,
            "away_team": poll.away,
            "votes": {k: tally.get(k, 0) for k in ("home", "draw", "away")},
            "total": total,
        }
        self.last_poll_result = result
        if total:
            shares = {k: round(100 * v / total) for k, v in result["votes"].items()}
            message = (
                f"Fans have voted on {poll.home} vs {poll.away}: {poll.home} {shares['home']}%, "
                f"draw {shares['draw']}%, {poll.away} {shares['away']}%. That's the fans' view, not a prediction!"
            )
        else:
            message = f"No votes for {poll.home} vs {poll.away} this time."
        return GameUpdate(kind="poll_closed", message=message, data=result)

    def due(self, now: float) -> list[GameUpdate]:
        """Close trivia rounds and polls whose time is up."""
        updates = []
        if self.trivia and now >= self.trivia.closes_at and (u := self.close_trivia()):
            updates.append(u)
        if self.poll and now >= self.poll.closes_at and (u := self.close_poll()):
            updates.append(u)
        return updates

    # -- status ---------------------------------------------------------------

    def status(self) -> GamificationStatus:
        trivia = self.trivia
        poll = self.poll
        return GamificationStatus(
            totals={k: self.totals[k] for k in ("viewers", "comments", "likes", "gifts", "follows", "shares")},
            milestones=[
                MilestoneStatus(
                    id=m.id,
                    label=m.label,
                    metric=m.metric,
                    target=m.target,
                    current=self._metric(m.metric),
                    reached=m.id in self.reached,
                )
                for m in MILESTONES
            ],
            outfit=self.outfit,
            background=self.background,
            trivia=(
                TriviaStatus(
                    question_en=trivia.question.question_en,
                    question_sw=trivia.question.question_sw,
                    options=[f"{LETTERS[i]}) {o}" for i, o in enumerate(trivia.question.options)],
                    closes_at=trivia.closes_at_wall,
                    answers=len(trivia.answered),
                    winners=trivia.winners,
                )
                if trivia
                else None
            ),
            poll=(
                PollStatus(
                    match_id=poll.match_id,
                    home_team=poll.home,
                    away_team=poll.away,
                    closes_at=poll.closes_at_wall,
                    votes={k: list(poll.votes.values()).count(k) for k in ("home", "draw", "away")},
                )
                if poll
                else None
            ),
            leaderboard=[
                LeaderboardEntry(viewer_name=self._names.get(k, k), points=p) for k, p in self.points.most_common(5)
            ],
            last_poll_result=self.last_poll_result,
        )


def _wall(seconds_from_now: float) -> datetime:
    return datetime.fromtimestamp(datetime.now(UTC).timestamp() + seconds_from_now, UTC)
