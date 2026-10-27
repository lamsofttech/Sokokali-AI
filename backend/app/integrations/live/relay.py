"""Moderator relay: real viewers' comments, typed or pasted in by a human moderator.

While Sokokali streams to TikTok LIVE, a moderator copies viewers' comments
(and notable gifts or joins) from TikTok into the dashboard. This source
produces no events of its own; relayed events arrive through
``POST /api/v1/live/relay`` and go through the same pipeline as any other
live event. It needs no platform API, so it is fully within TikTok's terms.
"""

import asyncio

from app.integrations.live.base import EventCallback, LiveEventSource


class ModeratorRelaySource(LiveEventSource):
    name = "tiktok-relay"
    is_simulated = False

    async def run(self, emit: EventCallback) -> None:
        await asyncio.Event().wait()  # events come from the moderator, not from here
