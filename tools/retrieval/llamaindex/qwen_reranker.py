import json
import random
import time
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.error import HTTPError, URLError

from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import MetadataMode, NodeWithScore, QueryBundle
from loggers.model_event_context import append_model_event, safe_endpoint


class QwenRerankPostprocessor(BaseNodePostprocessor):
    
    api_key: str
    api_base: str
    endpoint_format: str = "openai"
    model: str
    top_n: int = 3
    inject_instruct: bool = True
    instruct: str = (
        "Given a web search query, retrieve relevant passages that answer the query."
    )
    timeout: float = 60
    max_retries: int = 5
    initial_retry_delay: float = 0.5
    max_retry_delay: float = 8.0

    def __init__(
        self,
        api_key: str,
        base_url: str, 
        model: str,
        endpoint_format: str = "openai",
        top_n: int = 3,
        inject_instruct: bool = True,
        instruct: str = (
            "Given a web search query, retrieve relevant passages that answer the query."
        ),
        timeout: float = 60,
        max_retries: int = 5,
        initial_retry_delay: float = 0.5,
        max_retry_delay: float = 8.0,
        **kwargs,
    ) -> None:
        if not api_key:
            raise RuntimeError("api_key is required for QwenRerankPostprocessor")
        endpoint_format = endpoint_format.lower()
        if endpoint_format not in {"openai", "zjrcu"}:
            raise RuntimeError("endpoint_format must be 'openai' or 'zjrcu'")
        normalized_base = base_url.rstrip("/")
        if not normalized_base:
            raise RuntimeError("base_url is required for QwenRerankPostprocessor")
        

        super().__init__(
            api_key=api_key,
            api_base=normalized_base,
            endpoint_format=endpoint_format,
            model=model,
            top_n=top_n,
            inject_instruct=inject_instruct,
            instruct=instruct,
            timeout=timeout,
            max_retries=max_retries,
            initial_retry_delay=initial_retry_delay,
            max_retry_delay=max_retry_delay,
            **kwargs,
        )

    @staticmethod
    def _should_retry_http(status_code: int) -> bool:
        return status_code in {408, 409, 429} or status_code >= 500

    @staticmethod
    def _parse_retry_after(headers) -> float | None:
        if not headers:
            return None
        raw = headers.get("Retry-After")
        if not raw:
            return None
        try:
            seconds = float(raw)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(raw)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError):
                return None
        if 0 < seconds <= 60:
            return seconds
        return None

    def _calculate_retry_delay(self, attempt: int, headers=None) -> float:
        retry_after = self._parse_retry_after(headers)
        if retry_after is not None:
            return retry_after
        base_delay = min(
            self.initial_retry_delay * pow(2.0, min(attempt, 1000)),
            self.max_retry_delay,
        )
        return max(base_delay * (1 - 0.25 * random.random()), 0)

    def _request_json_with_retries(self, url: str, payload: dict) -> dict:
        last_error = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                last_error = exc
                if not self._should_retry_http(exc.code) or attempt >= self.max_retries:
                    raise RuntimeError(
                        "Reranker request failed after "
                        f"{attempt + 1} attempt(s): HTTP {exc.code} "
                        f"at {safe_endpoint(url)}"
                    ) from exc
                sleep_seconds = self._calculate_retry_delay(attempt, exc.headers)
                append_model_event(
                    "reranker_call_retry",
                    component="reranker",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    timeout_seconds=self.timeout,
                    sleep_seconds=round(sleep_seconds, 3),
                    error_type=type(exc).__name__,
                    status_code=exc.code,
                    endpoint=safe_endpoint(url),
                )
                time.sleep(sleep_seconds)
            except (TimeoutError, URLError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Reranker request timed out or failed after {attempt + 1} attempt(s): {exc}"
                    ) from exc
                sleep_seconds = self._calculate_retry_delay(attempt)
                append_model_event(
                    "reranker_call_retry",
                    component="reranker",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    timeout_seconds=self.timeout,
                    sleep_seconds=round(sleep_seconds, 3),
                    error_type=type(exc).__name__,
                    endpoint=safe_endpoint(url),
                )
                time.sleep(sleep_seconds)
        raise RuntimeError(f"Reranker request failed: {last_error}")

    def _postprocess_nodes(
        self,
        nodes: list[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> list[NodeWithScore]:
        if not nodes or query_bundle is None:
            return nodes

        documents = [
            node.get_content(metadata_mode=MetadataMode.NONE)
            for node in nodes
        ]

        top_n = min(self.top_n, len(documents))
        payload = {
            "model": self.model,
            "query": query_bundle.query_str,
            "documents": documents,
            "top_n": top_n,
        }
        if self.inject_instruct:
            payload["instruct"] = self.instruct

        body = None
        candidate_urls = [self.api_base]

        last_error = None
        for url in candidate_urls:
            try:
                body = self._request_json_with_retries(url, payload)
                break
            except HTTPError as exc:
                last_error = exc
                if exc.code != 404 or url == candidate_urls[-1]:
                    raise

        if body is None:
            raise RuntimeError(f"Rerank request failed: {last_error}")

        if "results" in body:
            results = body["results"]
        elif "output" in body and "results" in body["output"]:
            results = body["output"]["results"]
        else:
            raise RuntimeError(f"Unexpected rerank response: {body}")

        reranked_nodes: list[NodeWithScore] = []
        for item in results:
            original_node = nodes[item["index"]]
            reranked_nodes.append(
                NodeWithScore(
                    node=original_node.node,
                    score=item.get("relevance_score", original_node.score),
                )
            )

        return reranked_nodes
