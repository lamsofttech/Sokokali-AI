"""Sokokali's language understanding and response composition.

Phase 1 is deterministic and rule-based so it works offline and never invents
facts: every number in a reply comes from the sports service. Phase 2 adds a
configurable LLM behind this same interface, while keeping moderation and
grounding checks.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from app.schemas.chat import Intent, Language

_TOKEN_RE = re.compile(r"[a-z0-9']+(?:-[a-z]+)?")

_SWAHILI_WORDS = frozenset(
    "na ya wa ni nani atashinda itashinda kushinda shinda mechi timu leo kesho habari karibu asante "
    "sana gani je nini lini wapi matokeo ratiba utabiri takwimu sare bao magoli dhidi zijazo mchezo "
    "michezo hujambo jambo mambo wiki hii hiyo kwa za cha katika alishinda walishinda fomu msaada "
    "tafadhali nipe niambie ngoja zote mbili".split()
)
_SHENG_WORDS = frozenset(
    "niaje manze maze wasee msee buda fiti noma rada mbogi mathe atawin ata-win itawin itakam "
    "kuchapa kuchapwa venye bana mabeshte chali sanse wueh droo naeza".split()
)
_ENGLISH_WORDS = frozenset(
    "the will who what when win match game vs versus score result results prediction predict hello "
    "hi please can you me about today tomorrow next fixtures form how are and of is between".split()
)

_INTENT_KEYWORDS: list[tuple[Intent, frozenset[str]]] = [
    (
        Intent.GUARANTEE_REQUEST,
        frozenset("surebet fixed guarantee guaranteed uhakika hakika".split()),
    ),
    (
        Intent.PREDICTION,
        frozenset(
            "predict prediction predictions win winner wins atashinda itashinda kushinda shinda utabiri "
            "chance chances odds atawin ata-win itawin favourite favorite beat probability probabilities".split()
        ),
    ),
    (
        Intent.RESULTS,
        frozenset("score scores result results matokeo ilienda last alishinda walishinda".split()),
    ),
    (
        Intent.FIXTURES,
        frozenset(
            "fixture fixtures schedule upcoming ratiba next zijazo zinazokuja today tonight kesho leo "
            "weekend lini".split()
        ),
    ),
    (
        Intent.TEAM_FORM,
        frozenset("form fomu rating elo perform performance stats takwimu".split()),
    ),
]
_GREETING_WORDS = frozenset("hello hi hey habari mambo niaje sasa jambo hujambo sema vipi karibu".split())
_HELP_WORDS = frozenset("help msaada saidia unaweza naeza".split())

_ABUSIVE_WORDS = frozenset(
    "fuck fucking shit bitch asshole bastard cunt mjinga msenge malaya fala kumbafu mavi kuma".split()
)
_PERSONAL_INFO_RE = re.compile(
    r"(?:\+?254|\b0)[17]\d{8}\b"  # Kenyan mobile numbers
    r"|\b\d{9,}\b"  # other long digit runs (IDs, phone numbers)
    r"|[\w.+-]+@[\w-]+\.[\w.]+"  # email addresses
)

_SWAHILI_WEEKDAYS = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]

# Reply templates per key and language. Every value placeholder is filled from verified data.
_TEMPLATES: dict[str, dict[Language, str]] = {
    "greeting": {
        Language.ENGLISH: "Karibu! I'm Sokokali, your sports presenter. Ask me about fixtures, results, "
        "team form or match predictions!",
        Language.KISWAHILI: "Karibu sana! Mimi ni Sokokali, mtangazaji wako wa michezo. Niulize kuhusu mechi, "
        "ratiba, matokeo au utabiri!",
        Language.SHENG: "Niaje msee! Ni Sokokali hapa! Niulize kuhusu mechi, fixtures, results ama predictions!",
    },
    "prediction": {
        Language.ENGLISH: "What a matchup! {home} vs {away} ({competition}, {kickoff}). My model gives {home} "
        "{home_p}, a draw {draw_p}, and {away} {away_p}. Expected goals: {home_xg} to {away_xg}. "
        "Remember, these are probabilities, not guarantees!",
        Language.KISWAHILI: "Wadau! {home} dhidi ya {away} ni mechi kali sana! ({competition}, {kickoff}). "
        "Kulingana na takwimu: {home} kushinda {home_p}, sare {draw_p}, {away} kushinda {away_p}. "
        "Magoli yanayotarajiwa: {home_xg} kwa {away_xg}. Kumbuka, huu ni uwezekano tu, si uhakika!",
        Language.SHENG: "Wasee! {home} vs {away} itakuwa moto! ({competition}, {kickoff}). Stats zinasema "
        "{home} ana {home_p}, droo {draw_p}, {away} {away_p}. Lakini kumbuka, hii ni chance tu, si guarantee!",
    },
    "no_fixture": {
        Language.ENGLISH: "I don't have a scheduled {team_a} vs {team_b} match in my data, so I won't make up "
        "a prediction. Ask me for upcoming fixtures!",
        Language.KISWAHILI: "Sina mechi ya {team_a} dhidi ya {team_b} iliyopangwa kwenye data yangu, kwa hivyo "
        "sitabuni utabiri. Niulize ratiba ya mechi zijazo!",
        Language.SHENG: "Sina fixture ya {team_a} vs {team_b} kwa data yangu, so siwezi kubuni prediction. "
        "Niulize fixtures zinazokuja!",
    },
    "need_two_teams": {
        Language.ENGLISH: "Which match? Tell me two teams, for example 'Arsenal vs Chelsea'.",
        Language.KISWAHILI: "Mechi gani? Nitajie timu mbili, kwa mfano 'Arsenal na Chelsea'.",
        Language.SHENG: "Mechi gani msee? Nitajie timu mbili, kama 'Gor Mahia vs AFC Leopards'.",
    },
    "prediction_unavailable": {
        Language.ENGLISH: "I don't have enough verified data to predict {home} vs {away} right now, so I won't guess.",
        Language.KISWAHILI: "Sina takwimu za kutosha kutabiri {home} dhidi ya {away} kwa sasa, kwa hivyo sitakisia.",
        Language.SHENG: "Sina data ya kutosha ku-predict {home} vs {away} saa hii, so sitaguess.",
    },
    "fixtures_header": {
        Language.ENGLISH: "Upcoming matches:",
        Language.KISWAHILI: "Mechi zijazo:",
        Language.SHENG: "Fixtures zinazokuja:",
    },
    "no_fixtures": {
        Language.ENGLISH: "I have no upcoming fixtures in my data right now.",
        Language.KISWAHILI: "Sina ratiba ya mechi zijazo kwa sasa.",
        Language.SHENG: "Hakuna fixtures kwa data yangu saa hii.",
    },
    "last_meeting": {
        Language.ENGLISH: "Last time {home} met {away}: {home} {home_goals}-{away_goals} {away} ({date}).",
        Language.KISWAHILI: "Mara ya mwisho {home} walikutana na {away}: {home} {home_goals}-{away_goals} "
        "{away} ({date}).",
        Language.SHENG: "Last time {home} walicheza na {away}: {home} {home_goals}-{away_goals} {away} ({date}).",
    },
    "recent_results_header": {
        Language.ENGLISH: "Latest results for {team}:",
        Language.KISWAHILI: "Matokeo ya hivi karibuni ya {team}:",
        Language.SHENG: "Results za hivi karibuni za {team}:",
    },
    "need_team": {
        Language.ENGLISH: "Which team? Tell me a team name, for example 'Gor Mahia results'.",
        Language.KISWAHILI: "Timu gani? Nitajie jina la timu, kwa mfano 'matokeo ya Gor Mahia'.",
        Language.SHENG: "Timu gani msee? Nitajie timu, kama 'results za Gor'.",
    },
    "no_result": {
        Language.ENGLISH: "I don't have a verified result for that, so I won't guess.",
        Language.KISWAHILI: "Sina matokeo yaliyothibitishwa kuhusu hilo, kwa hivyo sitakisia.",
        Language.SHENG: "Sina result iliyo-verifiwa ya hiyo, so sitaguess.",
    },
    "team_form": {
        Language.ENGLISH: "{team} recent form (latest first): {form} (W=win, D=draw, L=loss).",
        Language.KISWAHILI: "Fomu ya {team} (ya karibuni kwanza): {form} (W=ushindi, D=sare, L=kushindwa).",
        Language.SHENG: "Form ya {team} (latest kwanza): {form} (W=win, D=droo, L=loss).",
    },
    "next_fixture": {
        Language.ENGLISH: "Next up: {home} vs {away} ({kickoff}).",
        Language.KISWAHILI: "Mechi ijayo: {home} dhidi ya {away} ({kickoff}).",
        Language.SHENG: "Next game: {home} vs {away} ({kickoff}).",
    },
    "guarantee": {
        Language.ENGLISH: "No one can guarantee a match result. There are no sure bets or fixed matches here. "
        "I share probabilities for information and entertainment only. If you bet, be 18+ and bet responsibly.",
        Language.KISWAHILI: "Hakuna anayeweza kuhakikisha matokeo ya mechi. Hakuna 'sure bet' wala mechi za "
        "kupangwa hapa. Ninatoa uwezekano kwa taarifa na burudani tu. Ukibeti, uwe na miaka 18 au zaidi na "
        "ubeti kwa uwajibikaji.",
        Language.SHENG: "Msee, hakuna mtu anaeza guarantee result. Hakuna sure bet ama fixed match hapa. "
        "Nashare chances tu kwa info na burudani. Ukibet, uwe 18+ na bet responsibly.",
    },
    "moderated_abuse": {
        Language.ENGLISH: "Let's keep the chat respectful, fam! Ask me anything about sports.",
        Language.KISWAHILI: "Tuweke mazungumzo kwa heshima, wadau! Niulize chochote kuhusu michezo.",
        Language.SHENG: "Wasee, tuchill na matusi! Niulize chochote ya sports.",
    },
    "moderated_personal_info": {
        Language.ENGLISH: "For your safety, please don't share phone numbers or personal details in the chat.",
        Language.KISWAHILI: "Kwa usalama wako, tafadhali usiweke nambari za simu au taarifa binafsi hapa.",
        Language.SHENG: "Kwa usalama yako, usishare number ya simu ama details zako hapa.",
    },
    "help": {
        Language.ENGLISH: "I can share upcoming fixtures, recent results, team form and match probabilities. "
        "Try: 'Arsenal vs Chelsea, who will win?' or 'fixtures'.",
        Language.KISWAHILI: "Naweza kukupa ratiba ya mechi, matokeo ya karibuni, fomu ya timu na uwezekano wa "
        "matokeo. Jaribu: 'Arsenal na Chelsea nani atashinda?' au 'ratiba'.",
        Language.SHENG: "Naeza kukupa fixtures, results, form ya timu na chances za mechi. "
        "Jaribu: 'Gor vs Leopards nani atawin?'",
    },
    "unknown": {
        Language.ENGLISH: "Asante for the comment! Ask me about fixtures, results, team form or predictions.",
        Language.KISWAHILI: "Asante kwa maoni yako! Niulize kuhusu ratiba, matokeo, fomu ya timu au utabiri.",
        Language.SHENG: "Asante kwa comment yako msee! Niulize kuhusu fixtures, results, form ama predictions.",
    },
    "simulated_notice": {
        Language.ENGLISH: "[Simulated data, not real statistics]",
        Language.KISWAHILI: "[Data ya majaribio, si takwimu halisi]",
        Language.SHENG: "[Hii ni data ya majaribio, si real stats]",
    },
}


@dataclass(frozen=True)
class MessageAnalysis:
    language: Language
    intent: Intent
    moderation_reason: str | None = None


class SokokaliAI:
    """Rule-based NLU and multilingual response templates."""

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return _TOKEN_RE.findall(text.lower())

    def detect_language(self, text: str) -> Language:
        tokens = self.tokenize(text)
        sw = sum(t in _SWAHILI_WORDS for t in tokens)
        sheng = sum(t in _SHENG_WORDS for t in tokens)
        en = sum(t in _ENGLISH_WORDS for t in tokens)
        if sheng >= 1 or (sw >= 1 and en >= 2):  # Sheng words, or heavy English/Swahili code-switching
            return Language.SHENG
        if sw >= 1 and sw >= en:
            return Language.KISWAHILI
        return Language.ENGLISH

    def moderate(self, text: str) -> str | None:
        """Return a reason when the message must not be answered normally."""
        if any(t in _ABUSIVE_WORDS for t in self.tokenize(text)):
            return "abuse"
        if _PERSONAL_INFO_RE.search(text):
            return "personal_info"
        return None

    def classify_intent(self, text: str, team_count: int) -> Intent:
        tokens = set(self.tokenize(text))
        lowered = text.lower()
        if "100%" in lowered or "sure bet" in lowered or "sure win" in lowered:
            tokens.add("guarantee")
        for intent, keywords in _INTENT_KEYWORDS:
            if tokens & keywords:
                return intent
        if team_count >= 2:
            return Intent.PREDICTION
        if team_count == 1:
            return Intent.TEAM_FORM
        if tokens & _GREETING_WORDS:
            return Intent.GREETING
        if tokens & _HELP_WORDS:
            return Intent.HELP
        return Intent.UNKNOWN

    def analyze(self, text: str, team_count: int, forced_language: Language | None = None) -> MessageAnalysis:
        language = forced_language or self.detect_language(text)
        reason = self.moderate(text)
        if reason is not None:
            return MessageAnalysis(language, Intent.MODERATED, reason)
        return MessageAnalysis(language, self.classify_intent(text, team_count))

    @staticmethod
    def compose(key: str, language: Language, **values: object) -> str:
        return _TEMPLATES[key][language].format(**values)

    @staticmethod
    def format_percent(probability: float) -> str:
        return f"{probability:.0%}"

    @staticmethod
    def format_kickoff(kickoff: datetime, language: Language) -> str:
        if language == Language.ENGLISH:
            return kickoff.strftime("%a %d %b, %H:%M UTC")
        return f"{_SWAHILI_WEEKDAYS[kickoff.weekday()]} {kickoff:%d/%m}, {kickoff:%H:%M} UTC"
