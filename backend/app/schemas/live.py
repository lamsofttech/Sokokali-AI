"""Livestream event contracts, shared by every platform connector."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class LiveEventKind(StrEnum):
    COMMENT = "comment"
    JOIN = "join"
    LIKE = "like"
    GIFT = "gift"
    FOLLOW = "follow"
    SHARE = "share"


class LiveEvent(BaseModel):
    """One normalized viewer event, whatever platform it came from."""

    event_id: str = Field(min_length=1, max_length=128, description="Unique per platform; used for deduplication")
    platform: str = Field(min_length=1, max_length=32, pattern=r"^[a-z0-9_-]+$")
    viewer_id: str = Field(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$", description="Opaque (hashed) viewer identifier"
    )
    viewer_name: str = Field(min_length=1, max_length=50, description="Public display name")
    kind: LiveEventKind
    text: str | None = Field(default=None, max_length=500)
    count: int = Field(default=1, ge=1, le=10_000, description="Likes in this batch, or gift repeats")
    gift_name: str | None = Field(default=None, max_length=50)
    platform_timestamp: datetime | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_simulated: bool = False


class BroadcastState(StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class IngestResult(BaseModel):
    accepted: bool
    reason: str | None = Field(default=None, description="Why a comment was not queued (duplicate, rate_limited, ...)")
    priority: int | None = None


class BroadcastStatus(BaseModel):
    state: BroadcastState
    source: str
    audience: str = Field(description="simulated, relay (moderator-typed real comments) or tiktok")
    source_is_simulated: bool
    source_error: str | None
    started_at: datetime | None
    uptime_seconds: float
    queue_size: int
    replies: int
    segments: int
    events_received: int
    comments_rejected: dict[str, int]
    errors: int
    last_error: str | None
    speaking_until: datetime | None
    connected_clients: int


class RelayEvent(BaseModel):
    """A real viewer action, typed in by a moderator watching the TikTok LIVE."""

    viewer_name: str = Field(min_length=1, max_length=50, examples=["wanjiku_254"])
    kind: LiveEventKind = LiveEventKind.COMMENT
    text: str | None = Field(default=None, max_length=500, examples=["Arsenal vs Chelsea nani atashinda?"])
    gift_name: str | None = Field(default=None, max_length=50)
    count: int = Field(default=1, ge=1, le=10_000)
