from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Iterator

from config import MODEL_SEMAPHORE_CONFIGS


class ModelSemaphoreTimeout(TimeoutError):
    pass


LLMGlobalSemaphoreTimeout = ModelSemaphoreTimeout


@dataclass(frozen=True)
class ModelSemaphoreConfig:
    enabled: bool
    redis_url: str
    key: str
    max_concurrent_requests: int
    wait_timeout_seconds: float
    lease_seconds: float
    poll_interval_seconds: float


@dataclass
class ModelSemaphoreLease:
    model_type: str
    enabled: bool
    acquired: bool = False
    key: str = ""
    member: str = ""
    wait_seconds: float = 0.0
    max_concurrent_requests: int = 0


LLMGlobalSemaphoreLease = ModelSemaphoreLease


class RedisModelSemaphore:
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

    def __init__(self, model_type: str, config: ModelSemaphoreConfig) -> None:
        self.model_type = model_type
        self.config = config
        self._sync_redis = None
        self._async_redis = None

    def _sync_client(self):
        if self._sync_redis is None:
            try:
                import redis
            except ImportError as exc:
                raise RuntimeError("redis package is required when model semaphore is enabled.") from exc
            self._sync_redis = redis.Redis.from_url(self.config.redis_url, decode_responses=True)
        return self._sync_redis

    async def _async_client(self):
        if self._async_redis is None:
            try:
                from redis import asyncio as redis_asyncio
            except ImportError as exc:
                raise RuntimeError("redis package is required when model semaphore is enabled.") from exc
            self._async_redis = redis_asyncio.from_url(self.config.redis_url, decode_responses=True)
        return self._async_redis

    def acquire_sync(self, *, caller_name: str, model: str) -> ModelSemaphoreLease:
        start = time.monotonic()
        deadline = start + self.config.wait_timeout_seconds
        member = self._member(caller_name, model)
        client = self._sync_client()
        lease_ms = int(self.config.lease_seconds * 1000)
        expire_seconds = int(self.config.lease_seconds) + 60

        while True:
            now_ms = int(time.time() * 1000)
            acquired = client.eval(
                self._ACQUIRE_SCRIPT,
                1,
                self.config.key,
                now_ms,
                now_ms + lease_ms,
                self.config.max_concurrent_requests,
                member,
                expire_seconds,
            )
            if int(acquired) == 1:
                return self._lease(member, start)
            if time.monotonic() >= deadline:
                raise self._timeout()
            time.sleep(self.config.poll_interval_seconds)

    async def acquire_async(self, *, caller_name: str, model: str) -> ModelSemaphoreLease:
        start = time.monotonic()
        deadline = start + self.config.wait_timeout_seconds
        member = self._member(caller_name, model)
        client = await self._async_client()
        lease_ms = int(self.config.lease_seconds * 1000)
        expire_seconds = int(self.config.lease_seconds) + 60

        while True:
            now_ms = int(time.time() * 1000)
            acquired = await client.eval(
                self._ACQUIRE_SCRIPT,
                1,
                self.config.key,
                now_ms,
                now_ms + lease_ms,
                self.config.max_concurrent_requests,
                member,
                expire_seconds,
            )
            if int(acquired) == 1:
                return self._lease(member, start)
            if time.monotonic() >= deadline:
                raise self._timeout()
            await asyncio.sleep(self.config.poll_interval_seconds)

    def release_sync(self, lease: ModelSemaphoreLease) -> None:
        if not lease.acquired or not lease.member:
            return
        self._sync_client().zrem(self.config.key, lease.member)

    async def release_async(self, lease: ModelSemaphoreLease) -> None:
        if not lease.acquired or not lease.member:
            return
        client = await self._async_client()
        await client.zrem(self.config.key, lease.member)

    def _member(self, caller_name: str, model: str) -> str:
        return f"{uuid.uuid4().hex}:{self.model_type}:{caller_name}:{model}"

    def _lease(self, member: str, start: float) -> ModelSemaphoreLease:
        return ModelSemaphoreLease(
            model_type=self.model_type,
            enabled=True,
            acquired=True,
            key=self.config.key,
            member=member,
            wait_seconds=round(time.monotonic() - start, 3),
            max_concurrent_requests=self.config.max_concurrent_requests,
        )

    def _timeout(self) -> ModelSemaphoreTimeout:
        return ModelSemaphoreTimeout(
            f"Timed out waiting for global {self.model_type} semaphore "
            f"key={self.config.key!r}, max_concurrent_requests={self.config.max_concurrent_requests}."
        )


def _build_config(model_type: str) -> ModelSemaphoreConfig:
    raw = MODEL_SEMAPHORE_CONFIGS[model_type]
    return ModelSemaphoreConfig(
        enabled=raw["enabled"],
        redis_url=raw["redis_url"],
        key=raw["key"],
        max_concurrent_requests=max(1, int(raw["max_concurrent_requests"])),
        wait_timeout_seconds=max(0.1, float(raw["wait_timeout_seconds"])),
        lease_seconds=max(1.0, float(raw["lease_seconds"])),
        poll_interval_seconds=max(0.05, float(raw["poll_interval_seconds"])),
    )


_SEMAPHORES = {
    model_type: RedisModelSemaphore(model_type, _build_config(model_type))
    for model_type in ("llm", "embedding", "reranker")
}


@asynccontextmanager
async def model_semaphore(model_type: str, caller_name: str, model: str) -> AsyncIterator[ModelSemaphoreLease]:
    config = _build_config(model_type)
    if not config.enabled:
        yield ModelSemaphoreLease(model_type=model_type, enabled=False)
        return

    semaphore = _SEMAPHORES[model_type]
    lease = await semaphore.acquire_async(caller_name=caller_name, model=model)
    try:
        yield lease
    finally:
        await semaphore.release_async(lease)


@contextmanager
def model_semaphore_sync(model_type: str, caller_name: str, model: str) -> Iterator[ModelSemaphoreLease]:
    config = _build_config(model_type)
    if not config.enabled:
        yield ModelSemaphoreLease(model_type=model_type, enabled=False)
        return

    semaphore = _SEMAPHORES[model_type]
    lease = semaphore.acquire_sync(caller_name=caller_name, model=model)
    try:
        yield lease
    finally:
        semaphore.release_sync(lease)


def semaphore_metadata(lease: ModelSemaphoreLease) -> dict[str, object]:
    if not lease.enabled:
        return {}
    prefix = f"{lease.model_type}_global_semaphore"
    return {
        f"{prefix}_key": lease.key,
        f"{prefix}_wait_seconds": lease.wait_seconds,
        f"{prefix}_max_requests": lease.max_concurrent_requests,
    }


@asynccontextmanager
async def llm_global_semaphore(agent_name: str, model: str) -> AsyncIterator[ModelSemaphoreLease]:
    async with model_semaphore("llm", agent_name, model) as lease:
        yield lease
