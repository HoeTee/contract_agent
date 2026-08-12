from __future__ import annotations

from typing import List

from llama_index.embeddings.openai_like import OpenAILikeEmbedding

from endpoints.runtime.llm_semaphore import model_semaphore, model_semaphore_sync
from loggers.model_event_context import append_model_event


class SemaphoreOpenAILikeEmbedding(OpenAILikeEmbedding):
    """OpenAI-like embedding client guarded by the global embedding semaphore."""

    def _get_query_embedding(self, query: str) -> List[float]:
        with model_semaphore_sync("embedding", "Embedding", self.model_name) as lease:
            self._log_wait(lease)
            return super()._get_query_embedding(query)

    def _get_text_embedding(self, text: str) -> List[float]:
        with model_semaphore_sync("embedding", "Embedding", self.model_name) as lease:
            self._log_wait(lease)
            return super()._get_text_embedding(text)

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        with model_semaphore_sync("embedding", "Embedding", self.model_name) as lease:
            self._log_wait(lease)
            return super()._get_text_embeddings(texts)

    async def _aget_query_embedding(self, query: str) -> List[float]:
        async with model_semaphore("embedding", "Embedding", self.model_name) as lease:
            self._log_wait(lease)
            return await super()._aget_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        async with model_semaphore("embedding", "Embedding", self.model_name) as lease:
            self._log_wait(lease)
            return await super()._aget_text_embedding(text)

    async def _aget_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        async with model_semaphore("embedding", "Embedding", self.model_name) as lease:
            self._log_wait(lease)
            return await super()._aget_text_embeddings(texts)

    @staticmethod
    def _log_wait(lease) -> None:
        if not lease.enabled:
            return
        append_model_event(
            "model_semaphore_acquired",
            component="embedding",
            semaphore_key=lease.key,
            wait_seconds=lease.wait_seconds,
            max_concurrent_requests=lease.max_concurrent_requests,
        )
