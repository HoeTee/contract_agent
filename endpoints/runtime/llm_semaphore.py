from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from config import (
    LLM_GLOBAL_SEMAPHORE_ENABLED,
    LLM_GLOBAL_SEMAPHORE_KEY,
    LLM_GLOBAL_SEMAPHORE_LEASE_SECONDS,
    LLM_GLOBAL_SEMAPHORE_MAX_REQUESTS,
    LLM_GLOBAL_SEMAPHORE_POLL_INTERVAL_SECONDS,
    LLM_GLOBAL_SEMAPHORE_REDIS_URL,
    LLM_GLOBAL_SEMAPHORE_WAIT_TIMEOUT_SECONDS,
)


class LLMGlobalSemaphoreTimeout(TimeoutError):
    pass


@dataclass
class LLMGlobalSemaphoreLease:
    enabled: bool
    acquired: bool = False
    key: str = ""
    member: str = ""
    wait_seconds: float = 0.0
    max_concurrent_requests: int = 0


class RedisLLMGlobalSemaphore:
    _ACQUIRE_SCRIPT = """
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
    local current = redis.call('ZCARD', KEYS[1])
    if current < tonumber(ARGV[3]) then
        redis.call('ZADD', KEYS[1], ARGV[2], ARGV[4])
        redis.call('EXPIRE', KEYS[1], ARGV[5])
        return 1
    end
    return 0
    """

    def __init__(
        self,
        *,
        redis_url: str,
        key: str,
        max_concurrent_requests: int,
        wait_timeout_seconds: float,
        lease_seconds: float,
        poll_interval_seconds: float,
    ) -> None:
        self.redis_url = redis_url
        self.key = key
        self.max_concurrent_requests = max(1, int(max_concurrent_requests))
        self.wait_timeout_seconds = max(0.1, float(wait_timeout_seconds))
        self.lease_seconds = max(1.0, float(lease_seconds))
        self.poll_interval_seconds = max(0.05, float(poll_interval_seconds))
        self._redis = None

    async def _client(self):
        if self._redis is None:
            try:
                from redis import asyncio as redis_asyncio
            except ImportError as exc:
                raise RuntimeError("redis package is required when llm.global_semaphore_enabled=true.") from exc
            self._redis = redis_asyncio.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def acquire(self, *, agent_name: str, model: str) -> LLMGlobalSemaphoreLease:
        start = time.monotonic()
        deadline = start + self.wait_timeout_seconds
        member = f"{uuid.uuid4().hex}:{agent_name}:{model}"
        client = await self._client()
        lease_ms = int(self.lease_seconds * 1000)
        expire_seconds = int(self.lease_seconds) + 60

        while True:
            now_ms = int(time.time() * 1000)
            expires_at_ms = now_ms + lease_ms
            acquired = await client.eval(
                self._ACQUIRE_SCRIPT,
                1,
                self.key,
                now_ms,
                expires_at_ms,
                self.max_concurrent_requests,
                member,
                expire_seconds,
            )
            if int(acquired) == 1:
                return LLMGlobalSemaphoreLease(
                    enabled=True,
                    acquired=True,
                    key=self.key,
                    member=member,
                    wait_seconds=round(time.monotonic() - start, 3),
                    max_concurrent_requests=self.max_concurrent_requests,
                )
            if time.monotonic() >= deadline:
                raise LLMGlobalSemaphoreTimeout(
                    "Timed out waiting for global LLM semaphore "
                    f"key={self.key!r}, max_concurrent_requests={self.max_concurrent_requests}."
                )
            await asyncio.sleep(self.poll_interval_seconds)

    async def release(self, lease: LLMGlobalSemaphoreLease) -> None:
        if not lease.acquired or not lease.member:
            return
        client = await self._client()
        await client.zrem(self.key, lease.member)


_SEMAPHORE = RedisLLMGlobalSemaphore(
    redis_url=LLM_GLOBAL_SEMAPHORE_REDIS_URL,
    key=LLM_GLOBAL_SEMAPHORE_KEY,
    max_concurrent_requests=LLM_GLOBAL_SEMAPHORE_MAX_REQUESTS,
    wait_timeout_seconds=LLM_GLOBAL_SEMAPHORE_WAIT_TIMEOUT_SECONDS,
    lease_seconds=LLM_GLOBAL_SEMAPHORE_LEASE_SECONDS,
    poll_interval_seconds=LLM_GLOBAL_SEMAPHORE_POLL_INTERVAL_SECONDS,
)


@asynccontextmanager
async def llm_global_semaphore(agent_name: str, model: str) -> AsyncIterator[LLMGlobalSemaphoreLease]:
    if not LLM_GLOBAL_SEMAPHORE_ENABLED:
        yield LLMGlobalSemaphoreLease(enabled=False)
        return

    lease = await _SEMAPHORE.acquire(agent_name=agent_name, model=model)
    try:
        yield lease
    finally:
        await _SEMAPHORE.release(lease)
