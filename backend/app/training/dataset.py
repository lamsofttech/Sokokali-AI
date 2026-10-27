"""Build the fine-tuning dataset from the historical football database.

Each example is one conversation in the same shape Sokokali uses live:

    system prompt -> question (English, Kiswahili or Sheng) -> tool call -> real tool result -> expert answer

The tool results are produced by the real tools over the real data, and every
number in an answer is checked against its tool result with the same grounding
check the live app uses. The model therefore learns *how* to analyse and talk
about football statistics, without learning invented numbers.

Run inside the backend container (it needs the database with history loaded):

    docker compose exec backend python -m app.training.dataset --out data/training
    docker compose cp backend:/app/data/training ./data/training

Output: train.jsonl and eval.jsonl in Hugging Face chat format
({"messages": [...], "tools": [...]}), ready for training/finetune_qlora.py.
"""

import argparse
import asyncio
import hashlib
import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.history.ingest import season_label
from app.history.service import HistoryService
from app.schemas.history import HeadToHead, LeagueTable, TeamStats
from app.services.llm_engine import SYSTEM_PROMPT, ungrounded_numbers
from app.services.llm_tools import ToolExecutor, ToolOutcome, tool_definitions

LANGS = ("en", "sw", "sheng")
LANGUAGE_NAMES = {"en": "English", "sw": "Kiswahili", "sheng": "Sheng (Nairobi slang mixing Kiswahili and English)"}

# ---------------------------------------------------------------------------------------------------------------
# Questions viewers and analysts ask, per language
# ---------------------------------------------------------------------------------------------------------------

H2H_Q = {
    "en": [
        "What's the history between {a} and {b}?",
        "How have {a} done against {b} over the years?",
        "Give me the head-to-head stats for {a} vs {b}.",
        "{a} vs {b}, who has the better record?",
        "Is {a} vs {b} usually a high-scoring game?",
    ],
    "sw": [
        "Historia ya {a} dhidi ya {b} ikoje?",
        "{a} na {b} wamekutana mara ngapi na nani ameshinda zaidi?",
        "Nipe takwimu za {a} dhidi ya {b}.",
        "Mechi za {a} na {b} huwa na magoli mengi?",
    ],
    "sheng": [
        "Niaje msee, history ya {a} na {b} iko aje?",
        "{a} vs {b}, nani ndio boss kwa history?",
        "Stats za {a} na {b} ziko aje wasee?",
        "Games za {a} na {b} huwa na goals mob?",
    ],
}
TEAM_Q = {
    "en": [
        "How have {t} been doing {venue_en}?",
        "Give me {t_pos} stats {venue_en} over the last {k} season{s}.",
        "What's {t_pos} form like?",
        "Are {t} strong {venue_en}?",
    ],
    "sw": [
        "{t} wanaendeleaje {venue_sw}?",
        "Nipe takwimu za {t} {venue_sw} kwa misimu {k} iliyopita.",
        "Fomu ya {t} ikoje?",
    ],
    "sheng": [
        "{t} wako aje {venue_sh}?",
        "Stats za {t} {venue_sh} kwa seasons {k} zilizopita?",
        "Form ya {t} iko aje msee?",
    ],
}
VENUES = {
    "all": {"venue_en": "recently", "venue_sw": "hivi karibuni", "venue_sh": "siku hizi"},
    "home": {"venue_en": "at home", "venue_sw": "nyumbani", "venue_sh": "wakiwa home"},
    "away": {"venue_en": "away from home", "venue_sw": "ugenini", "venue_sh": "wakiwa away"},
}
CHAMPION_Q = {
    "en": ["Who won the Premier League in {s}?", "Who were the champions in {s} and who went down?"],
    "sw": ["Nani alishinda Premier League msimu wa {s}?", "Bingwa wa {s} alikuwa nani?"],
    "sheng": ["Nani alichukua EPL season ya {s}?", "Champions wa {s} walikuwa akina nani msee?"],
}
FINISH_Q = {
    "en": ["Where did {t} finish in {s}?", "How did {t} do in the {s} season?"],
    "sw": ["{t} walimaliza nafasi ya ngapi msimu wa {s}?"],
    "sheng": ["{t} walimaliza position gani season ya {s}?"],
}

# ---------------------------------------------------------------------------------------------------------------
# Answers: grounded, expert-style analysis in each language
# ---------------------------------------------------------------------------------------------------------------


def _pct(x: float) -> str:
    return f"{round(x)}%"


def _one(x: float) -> str:
    return f"{x:.1f}"


def _score(m: Any) -> str:
    return f"{m.date:%d/%m/%Y} {m.home_team} {m.home_goals}-{m.away_goals} {m.away_team}"


def _recent_record(h: HeadToHead, k: int = 5) -> tuple[int, int, int, int]:
    w = d = lost = 0
    games = h.recent[:k]
    for m in games:
        mine, theirs = (m.home_goals, m.away_goals) if m.home_team == h.team_a else (m.away_goals, m.home_goals)
        w += mine > theirs
        d += mine == theirs
        lost += mine < theirs
    return len(games), w, d, lost


def h2h_answer(h: HeadToHead, lang: str, rng: random.Random) -> str:
    a, b = h.team_a, h.team_b
    k, rw, rd, rl = _recent_record(h)
    last = _score(h.recent[0]) if h.recent else ""
    a_lead = h.team_a_wins > 1.5 * max(h.team_b_wins, 1)
    b_lead = h.team_b_wins > 1.5 * max(h.team_a_wins, 1)
    high = h.over_2_5_pct >= 60
    low = h.over_2_5_pct <= 40
    if lang == "en":
        opener = rng.choice(["Great rivalry to look at!", "Let's look at the numbers.", "Here's the history, wadau."])
        lead = (
            f"{a} clearly have the upper hand." if a_lead else f"{b} clearly have the upper hand." if b_lead
            else "It's a very balanced rivalry."
        )
        goals = (
            "These games are usually open, with goals." if high else "These tend to be tight, low-scoring games."
            if low else "Goal-wise it's middle of the road."
        )
        return (
            f"{opener} {a} and {b} have met {h.matches} times in the Premier League since 1993/94: {a} won "
            f"{h.team_a_wins}, {b} won {h.team_b_wins}, and {h.draws} were draws. {lead} The average is "
            f"{_one(h.avg_total_goals)} goals per game, {_pct(h.over_2_5_pct)} went over 2.5 goals and both teams "
            f"scored in {_pct(h.btts_pct)}. {goals} {a} at home: {h.team_a_home_record} (W-D-L), away: "
            f"{h.team_a_away_record}. In the last {k} meetings {a} won {rw}, drew {rd} and lost {rl}; the latest was "
            f"{last}."
        )
    if lang == "sw":
        lead = (
            f"{a} wana ubabe wazi." if a_lead else f"{b} wana ubabe wazi." if b_lead
            else "Ni ushindani uliosawazishwa kabisa."
        )
        goals = (
            "Mechi hizi huwa wazi na zenye magoli." if high else "Mechi hizi huwa ngumu na zenye magoli machache."
            if low else "Kwa magoli, ni wastani tu."
        )
        return (
            f"Wadau! {a} na {b} wamekutana mara {h.matches} kwenye Premier League tangu 1993/94: {a} wameshinda "
            f"{h.team_a_wins}, {b} wameshinda {h.team_b_wins}, na sare {h.draws}. {lead} Wastani ni magoli "
            f"{_one(h.avg_total_goals)} kwa mechi, {_pct(h.over_2_5_pct)} ya mechi zilikuwa na magoli zaidi ya 2.5, "
            f"na timu zote mbili zilifunga katika {_pct(h.btts_pct)}. {goals} {a} wakiwa nyumbani: "
            f"{h.team_a_home_record} (ushindi-sare-kushindwa), ugenini: {h.team_a_away_record}. Katika mechi {k} za "
            f"mwisho, {a} wameshinda {rw}, sare {rd}, wamepoteza {rl}. Mechi ya mwisho: {last}."
        )
    lead = f"{a} ndio wababe hapa." if a_lead else f"{b} ndio wababe hapa." if b_lead else "Ni balance tu, hakuna boss."
    goals = "Hizi games huwa na goals mob." if high else "Hizi games huwa tight, goals ni chache." if low else "Goals ni kawaida tu."
    return (
        f"Wasee! {a} na {b} wamecheza mara {h.matches} kwa EPL since 1993/94: {a} wamewin {h.team_a_wins}, {b} "
        f"wamewin {h.team_b_wins}, droo {h.draws}. {lead} Average ni goals {_one(h.avg_total_goals)} kwa game, "
        f"{_pct(h.over_2_5_pct)} zilikuwa over 2.5, na both teams zilitoboa kwa {_pct(h.btts_pct)}. {goals} {a} "
        f"wakiwa home: {h.team_a_home_record}, away: {h.team_a_away_record}. Kwa games {k} za mwisho, {a} wamewin "
        f"{rw}, droo {rd}, wamechapwa {rl}. Game ya mwisho: {last}."
    )


LEVELS = {
    "en": ("title-winning level", "top-four level", "solid mid-table level", "lower mid-table level", "relegation-zone level"),
    "sw": ("kiwango cha ubingwa", "kiwango cha nne bora", "kiwango cha katikati ya jedwali", "chini ya katikati",
           "kiwango cha kushuka daraja"),
    "sheng": ("level ya champions", "level ya top four", "mid-table tu", "chini kidogo ya mid-table", "level ya relegation"),
}


def _level(ppg: float, lang: str) -> str:
    cut = 0 if ppg >= 2.2 else 1 if ppg >= 1.8 else 2 if ppg >= 1.3 else 3 if ppg >= 1.0 else 4
    return LEVELS[lang][cut]


SMALL_SAMPLE = {
    "en": " Small sample, so treat these numbers with caution.",
    "sw": " Hizi ni mechi chache, kwa hivyo takwimu hizi zichukuliwe kwa tahadhari.",
    "sheng": " Ni games chache tu, so usiamini hizi stats sana.",
}


def team_answer(s: TeamStats, lang: str, venue: str, rng: random.Random) -> str:
    return _team_answer(s, lang, venue, rng) + (SMALL_SAMPLE[lang] if s.played < 10 else "")


def _team_answer(s: TeamStats, lang: str, venue: str, rng: random.Random) -> str:
    seasons = len(s.seasons)
    level = _level(s.points_per_game, lang)
    shots = s.avg_shots_for is not None and s.avg_shots_on_target_for is not None
    if lang == "en":
        where = {"all": "", "home": " at home", "away": " away"}[venue]
        text = (
            f"{s.team}{where} over the last {seasons} season{'s' if seasons > 1 else ''}: played {s.played}, won "
            f"{s.wins}, drew {s.draws}, lost {s.losses}. That's {_one(s.points_per_game)} points per game, {level}. "
            f"They score {_one(s.avg_goals_for)} and concede {_one(s.avg_goals_against)} per game, kept clean sheets in "
            f"{_pct(s.clean_sheet_pct)} of games, and {_pct(s.over_2_5_pct)} of their games went over 2.5 goals."
        )
        if shots:
            text += f" They average {_one(s.avg_shots_for)} shots, {_one(s.avg_shots_on_target_for)} on target."
        return text + f" Form, latest first: {s.form_last_10} (current run: {s.current_streak})."
    if lang == "sw":
        where = {"all": "", "home": " wakiwa nyumbani", "away": " wakiwa ugenini"}[venue]
        text = (
            f"{s.team}{where} katika misimu {seasons} iliyopita: wamecheza {s.played}, wameshinda {s.wins}, sare "
            f"{s.draws}, wamepoteza {s.losses}. Hiyo ni pointi {_one(s.points_per_game)} kwa mechi, {level}. Wanafunga "
            f"{_one(s.avg_goals_for)} na kufungwa {_one(s.avg_goals_against)} kwa mechi, hawakufungwa katika "
            f"{_pct(s.clean_sheet_pct)} ya mechi, na {_pct(s.over_2_5_pct)} ya mechi zao zilikuwa na magoli zaidi ya 2.5."
        )
        if shots:
            text += f" Wastani wa mashuti ni {_one(s.avg_shots_for)}, {_one(s.avg_shots_on_target_for)} yakilenga lango."
        return text + f" Fomu (ya karibuni kwanza): {s.form_last_10} (W=ushindi, D=sare, L=kushindwa)."
    where = {"all": "", "home": " wakiwa home", "away": " wakiwa away"}[venue]
    text = (
        f"{s.team}{where} kwa seasons {seasons} zilizopita: wamecheza {s.played}, wamewin {s.wins}, droo {s.draws}, "
        f"wamechapwa {s.losses}. Hiyo ni points {_one(s.points_per_game)} kwa game, {level}. Wanatoboa "
        f"{_one(s.avg_goals_for)} na kufungwa {_one(s.avg_goals_against)} kwa game, clean sheets {_pct(s.clean_sheet_pct)}, "
        f"na {_pct(s.over_2_5_pct)} ya games zao zilikuwa over 2.5."
    )
    if shots:
        text += f" Wanapiga shots {_one(s.avg_shots_for)}, {_one(s.avg_shots_on_target_for)} on target."
    return text + f" Form (latest kwanza): {s.form_last_10}."


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _complete(table: LeagueTable) -> bool:
    games = {r.played for r in table.rows}
    return len(games) == 1 and next(iter(games)) == 2 * (len(table.rows) - 1)


def champion_answer(t: LeagueTable, lang: str) -> str:
    first, second = t.rows[0], t.rows[1]
    gap = first.points - second.points
    bottom = ", ".join(r.team for r in t.rows[-3:])
    s = t.season_label
    if lang == "en":
        return (
            f"{first.team} won the {s} Premier League with {first.points} points from {first.played} games "
            f"({first.wins} wins, {first.draws} draws, {first.losses} defeats), {gap} point{'s' if gap != 1 else ''} "
            f"ahead of {second.team}. The bottom three were {bottom}."
        )
    if lang == "sw":
        return (
            f"{first.team} walishinda Premier League msimu wa {s} wakiwa na pointi {first.points} kutoka mechi "
            f"{first.played} (ushindi {first.wins}, sare {first.draws}, kushindwa {first.losses}), pointi {gap} mbele ya "
            f"{second.team}. Timu tatu za mwisho zilikuwa {bottom}."
        )
    return (
        f"{first.team} ndio walichukua EPL season ya {s}, points {first.points} kutoka games {first.played} (wins "
        f"{first.wins}, droo {first.draws}, losses {first.losses}), points {gap} mbele ya {second.team}. Bottom three "
        f"walikuwa {bottom}."
    )


def finish_answer(t: LeagueTable, team: str, lang: str) -> str:
    row = next(r for r in t.rows if r.team == team)
    s = t.season_label
    so_far = not _complete(t)
    if lang == "en":
        when = "are currently" if so_far else "finished"
        return (
            f"In {s}, {team} {when} {_ordinal(row.position)} with {row.points} points from {row.played} games "
            f"({row.wins} wins, {row.draws} draws, {row.losses} defeats), goal difference {row.goal_difference:+d}."
        )
    if lang == "sw":
        when = "wako nafasi ya" if so_far else "walimaliza nafasi ya"
        return (
            f"Msimu wa {s}, {team} {when} {row.position} wakiwa na pointi {row.points} kutoka mechi {row.played} "
            f"(ushindi {row.wins}, sare {row.draws}, kushindwa {row.losses}), tofauti ya magoli {row.goal_difference:+d}."
        )
    when = "wako position" if so_far else "walimaliza position"
    return (
        f"Season ya {s}, {team} {when} {row.position}, points {row.points} kutoka games {row.played} (wins {row.wins}, "
        f"droo {row.draws}, losses {row.losses}), goal difference {row.goal_difference:+d}."
    )


# Guardrail conversations: no tools, the model must decline guarantees and stay honest about the future.
GUARDRAILS = [
    ("en", "Give me a sure bet for {a} vs {b}", "There's no such thing as a sure bet, my friend. Football is "
     "unpredictable and no one can guarantee a result. What I can do is give you the history and stats so you can "
     "follow the game with your eyes open. And if you bet, be 18+ and bet responsibly."),
    ("sw", "Nipe uhakika wa {a} dhidi ya {b}", "Hakuna uhakika kwenye soka, wadau. Hakuna anayeweza kuhakikisha "
     "matokeo. Ninachoweza kukupa ni historia na takwimu ili ufuatilie mechi ukiwa na taarifa. Na ukibeti, uwe na "
     "miaka 18 au zaidi na ubeti kwa uwajibikaji."),
    ("sheng", "Nipe sure bet ya {a} na {b} msee", "Msee, hakuna sure bet kwa soka. Hakuna mtu anaeza guarantee "
     "result. Naeza kukupa history na stats tu ndio uwe na info. Na ukibet, uwe 18+ na bet responsibly."),
    ("en", "What will the score be in {a} vs {b}?", "Nobody knows the score before kick-off, and I won't pretend to. "
     "Our analysts publish their pick before the game, and I can give you the head-to-head history and recent form to "
     "help you make sense of it."),
    ("sw", "Matokeo ya {a} dhidi ya {b} yatakuwa yapi?", "Hakuna anayejua matokeo kabla ya mechi, na sitajifanya "
     "najua. Wataalamu wetu hutoa utabiri wao kabla ya mechi, na naweza kukupa historia na fomu ya timu zote mbili."),
]


# ---------------------------------------------------------------------------------------------------------------
# Building conversations
# ---------------------------------------------------------------------------------------------------------------


@dataclass
class Example:
    kind: str
    lang: str
    messages: list[dict[str, Any]]

    def key(self) -> str:
        return hashlib.sha256(json.dumps(self.messages, sort_keys=True).encode()).hexdigest()


def hf_tools(forex_enabled: bool = True) -> list[dict[str, Any]]:
    """Sokokali's live tools in Hugging Face / OpenAI function format."""
    return [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in tool_definitions(forex_enabled)
    ]


def _conversation(lang: str, question: str, tool: str, args: dict[str, Any], result: str, answer: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"<context>\nreply_language: {LANGUAGE_NAMES[lang]}\n</context>\n{question}"},
        {"role": "assistant", "content": "", "tool_calls": [{"type": "function", "function": {"name": tool, "arguments": args}}]},
        {"role": "tool", "name": tool, "content": result},
        {"role": "assistant", "content": answer},
    ]


class DatasetBuilder:
    def __init__(self, history: HistoryService, executor: ToolExecutor, seed: int = 7) -> None:
        self.history = history
        self.executor = executor
        self.rng = random.Random(seed)
        self.rejected = 0

    async def _tool(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        return await self.executor.execute(name, args)

    def _grounded(self, answer: str, outcome: ToolOutcome) -> bool:
        ok = not outcome.is_error and not ungrounded_numbers(answer, [outcome])
        self.rejected += not ok
        return ok

    async def _add(
        self,
        out: list[Example],
        kind: str,
        lang: str,
        question: str,
        tool: str,
        args: dict[str, Any],
        answer_for: Callable[[ToolOutcome], str],
    ) -> None:
        outcome = await self._tool(tool, args)
        if outcome.is_error:
            return
        answer = answer_for(outcome)
        if self._grounded(answer, outcome):
            out.append(Example(kind, lang, _conversation(lang, question, tool, args, outcome.content, answer)))

    async def head_to_heads(self, min_meetings: int, per_pair: int) -> list[Example]:
        out: list[Example] = []
        teams = self.history.teams
        for i, a in enumerate(teams):
            for b in teams[i + 1 :]:
                h = self.history.head_to_head(a, b)
                if h.matches < min_meetings:
                    continue
                for _ in range(per_pair):
                    lang = self.rng.choice(LANGS)
                    first, second = (a, b) if self.rng.random() < 0.5 else (b, a)
                    q = self.rng.choice(H2H_Q[lang]).format(a=first, b=second)
                    await self._add(
                        out, "head_to_head", lang, q, "get_head_to_head_history", {"team_a": first, "team_b": second},
                        lambda o, lang=lang: h2h_answer(HeadToHead.model_validate_json(o.content), lang, self.rng),
                    )
        return out

    async def team_stats(self, recent_seasons: int, per_team: int) -> list[Example]:
        out: list[Example] = []
        recent = set(self.history.coverage().seasons[-recent_seasons:])
        teams = [t for t in self.history.teams if any(s.season in recent for s in self.history.team_history(t).seasons)]
        for team in teams:
            for _ in range(per_team):
                lang = self.rng.choice(LANGS)
                venue = self.rng.choice(["all", "home", "away"])
                k = self.rng.choice([1, 2, 3, 5])
                q = self.rng.choice(TEAM_Q[lang]).format(
                    t=team, t_pos=f"{team}'" if team.endswith("s") else f"{team}'s", k=k, s="s" if k > 1 else "",
                    **VENUES[venue],
                )
                await self._add(
                    out, "team_stats", lang, q, "get_team_history_stats", {"team": team, "venue": venue, "seasons": k},
                    lambda o, lang=lang, venue=venue: team_answer(TeamStats.model_validate_json(o.content), lang, venue, self.rng),
                )
        return out

    async def tables(self) -> list[Example]:
        out: list[Example] = []
        for season in self.history.coverage().seasons:
            label = season_label(season)
            table = self.history.league_table(season)
            for lang in LANGS:
                if _complete(table):
                    q = self.rng.choice(CHAMPION_Q[lang]).format(s=label)
                    await self._add(
                        out, "champion", lang, q, "get_league_table_history", {"season": label},
                        lambda o, lang=lang: champion_answer(LeagueTable.model_validate_json(o.content), lang),
                    )
                team = self.rng.choice(table.rows).team
                q = self.rng.choice(FINISH_Q[lang]).format(t=team, s=label)
                await self._add(
                    out, "finish", lang, q, "get_league_table_history", {"season": label},
                    lambda o, lang=lang, team=team: finish_answer(LeagueTable.model_validate_json(o.content), team, lang),
                )
        return out

    def guardrails(self, count: int) -> list[Example]:
        out = []
        teams = self.history.teams
        for _ in range(count):
            lang, q, answer = self.rng.choice(GUARDRAILS)
            a, b = self.rng.sample(teams, 2)
            out.append(
                Example(
                    "guardrail",
                    lang,
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"<context>\nreply_language: {LANGUAGE_NAMES[lang]}\n</context>\n{q.format(a=a, b=b)}"},
                        {"role": "assistant", "content": answer},
                    ],
                )
            )
        return out


def split(examples: list[Example], eval_fraction: float) -> tuple[list[Example], list[Example]]:
    """Deterministic split by content hash, so re-runs keep the same evaluation set."""
    train, test = [], []
    for e in examples:
        (test if int(e.key()[:8], 16) / 0xFFFFFFFF < eval_fraction else train).append(e)
    return train, test


def write_jsonl(path: Path, examples: list[Example], tools: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in examples:
            f.write(json.dumps({"messages": e.messages, "tools": tools, "kind": e.kind, "lang": e.lang}, ensure_ascii=False) + "\n")


async def build(
    history: HistoryService,
    executor: ToolExecutor,
    out_dir: Path,
    min_meetings: int = 6,
    per_pair: int = 2,
    recent_seasons: int = 10,
    per_team: int = 6,
    guardrails: int = 150,
    eval_fraction: float = 0.05,
    seed: int = 7,
) -> dict[str, Any]:
    builder = DatasetBuilder(history, executor, seed)
    examples = (
        await builder.head_to_heads(min_meetings, per_pair)
        + await builder.team_stats(recent_seasons, per_team)
        + await builder.tables()
        + builder.guardrails(guardrails)
    )
    unique = list({e.key(): e for e in examples}.values())
    train, test = split(unique, eval_fraction)
    tools = hf_tools()
    write_jsonl(out_dir / "train.jsonl", train, tools)
    write_jsonl(out_dir / "eval.jsonl", test, tools)
    summary: dict[str, Any] = {
        "train": len(train),
        "eval": len(test),
        "rejected_ungrounded": builder.rejected,
        "by_kind": {},
        "by_language": {},
    }
    for e in unique:
        summary["by_kind"][e.kind] = summary["by_kind"].get(e.kind, 0) + 1
        summary["by_language"][e.lang] = summary["by_language"].get(e.lang, 0) + 1
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


async def _main(args: argparse.Namespace) -> None:
    import logging

    from app.core.config import get_settings
    from app.core.container import build_container

    logging.disable(logging.WARNING)
    container = build_container(get_settings())
    await container.startup()
    try:
        if not container.history.loaded:
            raise SystemExit("No historical data: run `python -m app.history.ingest` first")
        executor = ToolExecutor(container.sports, container.predictions, container.forex)
        executor.history = container.history
        summary = await build(
            container.history, executor, Path(args.out), args.min_meetings, args.per_pair, args.recent_seasons,
            args.per_team, args.guardrails, args.eval_fraction, args.seed,
        )
        print(json.dumps(summary, indent=2))
    finally:
        await container.aclose()


def main() -> None:
    p = argparse.ArgumentParser(description="Build Sokokali's fine-tuning dataset from the historical database")
    p.add_argument("--out", default="data/training")
    p.add_argument("--min-meetings", type=int, default=6, help="only rivalries with at least this many meetings")
    p.add_argument("--per-pair", type=int, default=2, help="head-to-head examples per rivalry")
    p.add_argument("--recent-seasons", type=int, default=10, help="team-stat examples for clubs in these seasons")
    p.add_argument("--per-team", type=int, default=6)
    p.add_argument("--guardrails", type=int, default=150)
    p.add_argument("--eval-fraction", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=7)
    asyncio.run(_main(p.parse_args()))


if __name__ == "__main__":
    main()
