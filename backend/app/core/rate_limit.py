"""Sliding-window rate limiters.

``SlidingWindowRateLimiter`` keeps hits in process memory (one server).
``RedisRateLimiter`` keeps them in Redis, so limits survive restarts and are
shared by every replica. If Redis is unreachable it falls back to the
in-memory limiter instead of blocking or failing requests.
"""

import logging
import time
import uuid
from collections import defaultdict, deque

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        hits = self._hits[key]
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        return True

    async def check(self, key: str) -> bool:
        return self.allow(key)


class RedisRateLimiter:
    def __init__(self, redis: Redis, limit: int, window_seconds: float = 60.0, prefix: str = "sokokali:rl:") -> None:
        self.redis = redis
        self.limit = limit
        self.window_seconds = window_seconds
        self.prefix = prefix
        self.fallback = SlidingWindowRateLimiter(limit, window_seconds)
        self._warned = False

    async def check(self, key: str) -> bool:
        now_ms = int(time.time() * 1000)
        window_ms = int(self.window_seconds * 1000)
        redis_key = self.prefix + key
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(redis_key, 0, now_ms - window_ms)
                pipe.zcard(redis_key)
                count = (await pipe.execute())[1]
            if count >= self.limit:
                return False
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.zadd(redis_key, {f"{now_ms}-{uuid.uuid4().hex[:8]}": now_ms})
                pipe.pexpire(redis_key, window_ms)
                await pipe.execute()
            self._warned = False
            return True
        except (RedisError, OSError) as exc:
            if not self._warned:
                logger.warning("redis_rate_limit_unavailable", extra={"error": str(exc), "fallback": "in-memory"})
                self._warned = True
            return self.fallback.allow(key)
