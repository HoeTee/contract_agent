from __future__ import annotations

import sys

__all__ = ["LlamaIndexRAG", "build_llamaindex_env_error", "load_llamaindex_rag"]


def load_llamaindex_rag():
    from tools.retrieval.llamaindex.rag_engine import LlamaIndexRAG

    return LlamaIndexRAG


def build_llamaindex_env_error(exc: BaseException) -> RuntimeError:
    return RuntimeError(
        "LlamaIndex dependencies are unavailable in the current Python environment. "
        f"Interpreter: {sys.executable}. Original error: {exc}. "
        "If the packages are already installed in the project virtualenv, restart the backend with "
        r".venv\Scripts\python.exe -m uvicorn api.main:app --port 8000."
    )


def __getattr__(name: str):
    if name == "LlamaIndexRAG":
        return load_llamaindex_rag()
    raise AttributeError(name)
