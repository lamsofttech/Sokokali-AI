"""TikTok LIVE connector placeholder.

TikTok does not currently offer a public, officially authorized API for
receiving LIVE comments, gifts and joins. The tools that do this work by
reverse-engineering TikTok's private systems, which this project does not use
(no unauthorized bypasses, no credential scraping).

This class reserves the slot so the rest of the pipeline is ready: when
authorized access exists (an approved TikTok partner programme or a licensed
provider with TikTok's permission), implement ``run`` to translate the official
events into ``LiveEvent`` objects. Until then it refuses to start.
"""

from app.integrations.live.base import EventCallback, LiveEventSource, LiveSourceUnavailableError


class TikTokLiveSource(LiveEventSource):
    name = "tiktok"
    is_simulated = False

    async def check(self) -> None:
        raise LiveSourceUnavailableError(
            "TikTok LIVE is not connected: it needs officially authorized API access, which is not configured. "
            "Use SOKOKALI_LIVE_SOURCE=simulated meanwhile."
        )

    async def run(self, emit: EventCallback) -> None:
        await self.check()  # always raises until authorized access is implemented
