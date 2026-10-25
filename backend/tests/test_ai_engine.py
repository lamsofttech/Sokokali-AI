import pytest

from app.schemas.chat import Intent, Language
from app.services.ai_engine import SokokaliAI

ai = SokokaliAI()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Sokokali, Arsenal na Chelsea nani atashinda?", Language.KISWAHILI),
        ("Habari", Language.KISWAHILI),
        ("Who will win between Arsenal and Chelsea?", Language.ENGLISH),
        ("Hello there", Language.ENGLISH),
        ("Niaje msee, Gor itawin leo?", Language.SHENG),
        ("Arsenal na Chelsea who will win?", Language.SHENG),
    ],
)
def test_detect_language(text: str, expected: Language) -> None:
    assert ai.detect_language(text) == expected


@pytest.mark.parametrize(
    ("text", "teams", "expected"),
    [
        ("Arsenal na Chelsea nani atashinda?", 2, Intent.PREDICTION),
        ("Arsenal vs Chelsea", 2, Intent.PREDICTION),
        ("What are the upcoming fixtures?", 0, Intent.FIXTURES),
        ("Matokeo ya Gor Mahia", 1, Intent.RESULTS),
        ("Gor Mahia", 1, Intent.TEAM_FORM),
        ("Give me a sure bet", 0, Intent.GUARANTEE_REQUEST),
        ("Is this match fixed?", 0, Intent.GUARANTEE_REQUEST),
        ("Mambo!", 0, Intent.GREETING),
        ("help", 0, Intent.HELP),
        ("I like pizza", 0, Intent.UNKNOWN),
    ],
)
def test_classify_intent(text: str, teams: int, expected: Intent) -> None:
    assert ai.classify_intent(text, teams) == expected


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("you are an idiot fala", "abuse"),
        ("Call me on 0712345678", "personal_info"),
        ("my email is fan@example.com", "personal_info"),
        ("Arsenal vs Chelsea", None),
    ],
)
def test_moderation(text: str, reason: str | None) -> None:
    assert ai.moderate(text) == reason


def test_forced_language_overrides_detection() -> None:
    assert ai.analyze("Hello", 0, Language.KISWAHILI).language == Language.KISWAHILI


def test_every_template_exists_in_every_language() -> None:
    from app.services.ai_engine import _TEMPLATES

    for key, translations in _TEMPLATES.items():
        assert set(translations) == set(Language), key
