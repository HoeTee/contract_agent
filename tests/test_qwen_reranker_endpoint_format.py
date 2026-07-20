from tools.retrieval.llamaindex.qwen_reranker import QwenRerankPostprocessor


def test_openai_reranker_endpoint_normalization():
    assert (
        QwenRerankPostprocessor.normalize_api_base(
            "https://gateway.example.com/compatible-api/v1",
            "openai",
        )
        == "https://gateway.example.com/compatible-api/v1/reranks"
    )
    assert (
        QwenRerankPostprocessor.normalize_api_base(
            "https://gateway.example.com/compatible-mode/v1",
            "openai",
        )
        == "https://gateway.example.com/compatible-mode/v1/reranks"
    )
    assert (
        QwenRerankPostprocessor.normalize_api_base(
            "https://gateway.example.com/v1",
            "openai",
        )
        == "https://gateway.example.com/v1/reranks"
    )


def test_zjrcu_reranker_endpoint_normalization():
    assert (
        QwenRerankPostprocessor.normalize_api_base(
            "https://gateway.example.com/api/v1",
            "zjrcu",
        )
        == "https://gateway.example.com/api/v1/rerank"
    )
    assert (
        QwenRerankPostprocessor.normalize_api_base(
            "https://gateway.example.com/api/v1/rerank",
            "zjrcu",
        )
        == "https://gateway.example.com/api/v1/rerank"
    )
