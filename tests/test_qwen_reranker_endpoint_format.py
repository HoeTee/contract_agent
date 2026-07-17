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
        == "https://gateway.example.com/compatible-mode/v1"
    )


def test_dashscope_reranker_endpoint_normalization():
    assert (
        QwenRerankPostprocessor.normalize_api_base(
            "https://gateway.example.com/compatible-mode/v1",
            "dashscope",
        )
        == "https://gateway.example.com/api/v1/services/rerank/text-rerank/text-rerank"
    )
    assert (
        QwenRerankPostprocessor.normalize_api_base(
            "https://gateway.example.com/api/v1/services/rerank/text-rerank/text-rerank",
            "dashscope",
        )
        == "https://gateway.example.com/api/v1/services/rerank/text-rerank/text-rerank"
    )
