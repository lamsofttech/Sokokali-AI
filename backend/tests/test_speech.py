from fastapi.testclient import TestClient

from app.schemas.chat import Intent, Language
from app.schemas.speech import AvatarAnimation
from app.services.speech_service import build_speech_cue, speakable_text


def test_speakable_text_removes_on_screen_notices_and_symbols() -> None:
    reply = "EUR/USD hourly outlook: SELL. Arsenal 2-1 Chelsea. [Simulated data, not real statistics]"
    assert speakable_text(reply, Language.ENGLISH) == "EUR USD hourly outlook: SELL. Arsenal 2 1 Chelsea."
    assert speakable_text("Gor 2-0 Ingwe [Data ya majaribio]", Language.KISWAHILI) == "Gor 2 kwa 0 Ingwe"


def test_vs_is_spoken_in_the_reply_language() -> None:
    assert speakable_text("Arsenal vs Chelsea", Language.ENGLISH) == "Arsenal versus Chelsea"
    assert speakable_text("Gor vs Leopards", Language.SHENG) == "Gor dhidi ya Leopards"


def test_cue_language_and_animation() -> None:
    cue = build_speech_cue("Karibu sana!", Language.KISWAHILI, Intent.GREETING, is_simulated=False)
    assert cue.voice_languages[0] == "sw-KE"
    assert cue.animation == AvatarAnimation.CELEBRATION
    assert build_speech_cue("x", Language.ENGLISH, Intent.PREDICTION, True).animation == AvatarAnimation.COMMENTARY
    assert build_speech_cue("x", Language.ENGLISH, Intent.UNKNOWN, False).animation == AvatarAnimation.SPEAKING


def test_chat_response_includes_speech_cue(client: TestClient) -> None:
    body = client.post("/api/v1/chat", json={"message": "Sokokali, Arsenal na Chelsea nani atashinda?"}).json()
    speech = body["speech"]
    assert speech["voice_languages"][0] == "sw-KE"
    assert speech["animation"] == "commentary"
    assert speech["show_simulated_banner"] is True
    assert "[" not in speech["text"] and "majaribio" in body["reply"]  # notice on screen, not spoken
