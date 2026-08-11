import re


class ModelCallError(RuntimeError):
    """Raised when an external model-style API fails after timeout/retries."""

    EVENT_BY_COMPONENT = {
        "agent": "agent_model_call_failed",
        "embedding": "embedding_call_failed",
        "reranker": "reranker_call_failed",
    }

    LABEL_BY_COMPONENT = {
        "agent": "Agent 模型",
        "embedding": "Embedding 模型",
        "reranker": "Reranker 模型",
    }

    def __init__(self, component: str, detail: str, http_status: int | None = None) -> None:
        self.component = component
        self.detail = detail
        self.http_status = http_status
        self.event_type = self.EVENT_BY_COMPONENT.get(component, "model_call_failed")
        label = self.LABEL_BY_COMPONENT.get(component, "模型")
        self.user_message = f"模型调用超时或重试失败（{label}）"
        super().__init__(f"模型调用超时或重试失败（{label}）：{detail}")

    def as_task_error(self) -> dict:
        return {
            "code": self.event_type,
            "message": self.user_message,
            "component": self.component,
            "http_status": self.http_status,
            "detail": str(self),
        }


def _extract_http_status(detail: str) -> int | None:
    match = re.search(r"(?:error code|status|http)\D*(\d{3})", detail, flags=re.IGNORECASE)
    if not match:
        return None
    status = int(match.group(1))
    if 100 <= status <= 599:
        return status
    return None


def classify_model_call_error(
    detail: str,
    default_component: str = "agent",
    http_status: int | None = None,
) -> ModelCallError:
    """Classify a lower-level model error message into a UI/event error."""

    lowered = detail.lower()
    if "rerank" in lowered or "reranker" in lowered:
        component = "reranker"
    elif "embed" in lowered or "embedding" in lowered:
        component = "embedding"
    else:
        component = default_component
    return ModelCallError(component, detail, http_status=http_status or _extract_http_status(detail))
