from enum import StrEnum

from pydantic import BaseModel, Field


class AvatarAnimation(StrEnum):
    IDLE = "idle"
    SPEAKING = "speaking"
    COMMENTARY = "commentary"
    CELEBRATION = "celebration"


class SpeechCue(BaseModel):
    text: str = Field(description="Reply cleaned up for text-to-speech (on-screen notices removed)")
    voice_languages: list[str] = Field(description="BCP 47 voice languages to try, best first")
    animation: AvatarAnimation = Field(description="Avatar animation to play while speaking")
    show_simulated_banner: bool = Field(description="Show the simulated-data banner on the avatar stage")
