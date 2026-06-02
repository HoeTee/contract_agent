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

    def __init__(self, component: str, detail: str) -> None:
        self.component = component
        self.detail = detail
        self.event_type = self.EVENT_BY_COMPONENT.get(component, "model_call_failed")
        label = self.LABEL_BY_COMPONENT.get(component, "模型")
        super().__init__(f"模型调用超时或重试失败（{label}）：{detail}")


def classify_model_call_error(detail: str, default_component: str = "agent") -> ModelCallError:
    """Classify a lower-level model error message into a UI/event error."""

    lowered = detail.lower()
    if "rerank" in lowered or "reranker" in lowered:
        component = "reranker"
    elif "embed" in lowered or "embedding" in lowered:
        component = "embedding"
    else:
        component = default_component
    return ModelCallError(component, detail)
