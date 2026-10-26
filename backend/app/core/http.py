"""HTTP helper for external data providers: timeouts, retries with exponential backoff and jitter."""

import asyncio
import logging
import random
from typing import Any

import httpx

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class UpstreamError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Any:
    """GET ``url`` and decode JSON, retrying timeouts, connection errors, 429 and 5xx.

    A ``Retry-After`` header (seconds) is honoured, capped at ``max_delay``.
    Other 4xx responses fail immediately: retrying a bad key or a wrong URL never helps.
    """
    for attempt in range(1, max_attempts + 1):
        retry_after: float | None = None
        try:
            response = await client.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            error = UpstreamError(f"{type(exc).__name__} calling {url}")
        else:
            if response.status_code < 400:
                try:
                    return response.json()
                except ValueError:
                    raise UpstreamError(f"Invalid JSON from {url}", response.status_code) from None
            error = UpstreamError(f"HTTP {response.status_code} from {url}", response.status_code)
            if response.status_code not in RETRYABLE_STATUS:
                raise error
            header = response.headers.get("Retry-After")
            retry_after = float(header) if header and header.isdigit() else None

        if attempt == max_attempts:
            raise error
        delay = retry_after if retry_after is not None else base_delay * 2 ** (attempt - 1) + random.uniform(0, 0.5)
        delay = min(delay, max_delay)
        logger.warning("upstream_retry", extra={"url": url, "attempt": attempt, "delay_s": round(delay, 2)})
        await asyncio.sleep(delay)
    raise AssertionError("unreachable")
