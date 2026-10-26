"""Turns a chat reply into a speech cue for the avatar: speakable text, voice language and animation.

Text-to-speech itself runs in the browser for now (Web Speech API, free). Keeping
the cue on the server means the broadcast controller (Phase 6) can drive the same
avatar without duplicating these rules in the frontend.
"""

import re

from app.schemas.chat import Intent, Language
from app.schemas.speech import AvatarAnimation, SpeechCue

# BCP 47 tags the browser should try, best first. Sheng is mostly Kiswahili phonetically.
VOICE_LANGUAGES: dict[Language, list[str]] = {
    Language.ENGLISH: ["en-KE", "en-GB", "en-US", "en"],
    Language.KISWAHILI: ["sw-KE", "sw-TZ", "sw", "en-KE"],
    Language.SHENG: ["sw-KE", "sw-TZ", "sw", "en-KE"],
}

_ANIMATIONS: dict[Intent, AvatarAnimation] = {
    Intent.GREETING: AvatarAnimation.CELEBRATION,
    Intent.PREDICTION: AvatarAnimation.COMMENTARY,
    Intent.FIXTURES: AvatarAnimation.COMMENTARY,
    Intent.RESULTS: AvatarAnimation.COMMENTARY,
    Intent.TEAM_FORM: AvatarAnimation.COMMENTARY,
    Intent.FOREX: AvatarAnimation.COMMENTARY,
}

_BRACKETED = re.compile(r"\s*\[[^\]]*\]")  # "[Simulated data, ...]" stays on screen, not in the voice
_PAIR = re.compile(r"\b([A-Z]{3})/([A-Z]{3})\b")
_SCORE = re.compile(r"\b(\d+)-(\d+)\b")
_SPACES = re.compile(r"\s+")


def speakable_text(reply: str, language: Language) -> str:
    text = _BRACKETED.sub("", reply)
    text = _PAIR.sub(r"\1 \2", text)  # "EUR/USD" -> "EUR USD", not "EUR slash USD"
    text = _SCORE.sub(r"\1 \2" if language == Language.ENGLISH else r"\1 kwa \2", text)
    text = text.replace(" vs ", " versus " if language == Language.ENGLISH else " dhidi ya ")
    return _SPACES.sub(" ", text).strip()


def build_speech_cue(reply: str, language: Language, intent: Intent, is_simulated: bool) -> SpeechCue:
    return SpeechCue(
        text=speakable_text(reply, language),
        voice_languages=VOICE_LANGUAGES[language],
        animation=_ANIMATIONS.get(intent, AvatarAnimation.SPEAKING),
        show_simulated_banner=is_simulated,
    )
