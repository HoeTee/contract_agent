"""
Central configuration for the contract review workflow.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


PROJECT_ROOT_PATH = Path(__file__).resolve().parent
PROJECT_ROOT = str(PROJECT_ROOT_PATH)
ENV_PATH = PROJECT_ROOT_PATH / ".env"
CONFIG_PATH = PROJECT_ROOT_PATH / "config.yaml"

if not ENV_PATH.exists():
    raise RuntimeError(f"Missing required .env file: {ENV_PATH}")
if not CONFIG_PATH.exists():
    raise RuntimeError(f"Missing required config.yaml file: {CONFIG_PATH}")

load_dotenv(ENV_PATH)


def _load_yaml_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise RuntimeError("config.yaml must contain a top-level mapping.")
    return data


CONFIG = _load_yaml_config()


def cfg(section: str, key: str) -> Any:
    section_data = CONFIG.get(section)
    if not isinstance(section_data, dict):
        raise RuntimeError(f"Missing config.yaml section: {section}")
    if key not in section_data:
        raise RuntimeError(f"Missing config.yaml field: {section}.{key}")
    return section_data[key]


def env_required(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required .env field: {name}")
    return value.strip()


def env_optional(name: str) -> str:
    value = os.getenv(name)
    if value is None:
        return ""
    return value.strip()


def env_bool(name: str, default: bool | None) -> bool | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return _parse_bool(raw, name)


def _parse_bool(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if raw == "":
            return None
        normalized = raw.lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise RuntimeError(f"{field_name} must be true or false, got {value!r}.")


def _as_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{field_name} must be an integer, got {value!r}.") from exc


def _as_float(value: Any, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{field_name} must be a number, got {value!r}.") from exc


def _as_str(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError(f"{field_name} must be a string, got {value!r}.")
    return value.strip()


def _as_str_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = value
    else:
        raise RuntimeError(f"{field_name} must be a string or list, got {value!r}.")
    result = tuple(str(item).strip() for item in items if str(item).strip())
    if not result:
        raise RuntimeError(f"{field_name} must contain at least one value.")
    return result


def _as_size_bytes(value: Any, field_name: str) -> int:
    if isinstance(value, int):
        if value <= 0:
            raise RuntimeError(f"{field_name} must be greater than 0.")
        return value
    raw = _as_str(value, field_name)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(kb|mb|gb|b)?", raw.lower())
    if not match:
        raise RuntimeError(f"{field_name} must be a size like '512KB', '50MB', '1GB', or bytes.")
    amount = float(match.group(1))
    unit = match.group(2) or "b"
    multipliers = {
        "b": 1,
        "kb": 1024,
        "mb": 1024 * 1024,
        "gb": 1024 * 1024 * 1024,
    }
    size = int(amount * multipliers[unit])
    if size <= 0:
        raise RuntimeError(f"{field_name} must be greater than 0.")
    return size


def _project_path(value: Any, field_name: str) -> str:
    raw = _as_str(value, field_name)
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT_PATH / path
    return str(path)


MCP_SERVER_PATH = str(PROJECT_ROOT_PATH / "mcp_service" / "mcp_server" / "mcp_server.py")
MCP_SERVER_URL = "http://localhost:8000/mcp"
DOCS_DIR = str(PROJECT_ROOT_PATH / "docs")
DEFAULT_REVIEW_CRITERIA_PATH = str(PROJECT_ROOT_PATH / "resources" / "review_criteria" / "criteria.docx")
REPORTS_DIR = str(PROJECT_ROOT_PATH / "reports")
LOGS_DIR = str(PROJECT_ROOT_PATH / "logs" / "workflow")

LLM_API_KEY = env_required("LLM_API_KEY")
EMBED_API_KEY = env_required("EMBED_API_KEY")
SESSION_SECRET_KEY = env_required("SESSION_SECRET_KEY")

LLM_BASE_URL = _as_str(cfg("llm", "base_url"), "llm.base_url")
LLM_NAME = _as_str(cfg("llm", "name"), "llm.name")
LLM_ENABLE_THINKING = _parse_bool(cfg("llm", "enable_thinking"), "llm.enable_thinking")
MAX_CONTEXT_TOKENS = _as_int(cfg("llm", "max_context_tokens"), "llm.max_context_tokens")
MAX_RESULT_TOKENS = _as_int(cfg("llm", "max_result_tokens"), "llm.max_result_tokens")
MAX_TOOL_CALLS = _as_int(cfg("llm", "max_tool_calls"), "llm.max_tool_calls")
TEMPERATURE = _as_float(cfg("llm", "temperature"), "llm.temperature")
TOP_P = _as_float(cfg("llm", "top_p"), "llm.top_p")
SEED = _as_int(cfg("llm", "seed"), "llm.seed")

EMBED_BASE_URL = _as_str(cfg("embedding", "base_url"), "embedding.base_url")
EMBED_NAME = _as_str(cfg("embedding", "name"), "embedding.name")

RERANK_BASE_URL = _as_str(cfg("rerank", "base_url"), "rerank.base_url")
RERANK_NAME = _as_str(cfg("rerank", "name"), "rerank.name")
RERANK_PROVIDER = _as_str(
    cfg("rerank", "provider"),
    "rerank.provider",
).lower()
if RERANK_PROVIDER not in {"higress_qwen", "bge", "dashscope_qwen"}:
    raise RuntimeError(
        "rerank.provider must be one of 'higress_qwen', 'bge', or 'dashscope_qwen', "
        f"got {RERANK_PROVIDER!r}."
    )
RERANK_INSTRUCT = _as_str(cfg("rerank", "instruct"), "rerank.instruct")
RERANK_API_KEY = env_optional("RERANK_API_KEY")
if RERANK_PROVIDER in {"higress_qwen", "dashscope_qwen"} and not RERANK_API_KEY:
    raise RuntimeError(f"Missing required .env field: RERANK_API_KEY for rerank.provider={RERANK_PROVIDER!r}")

MAX_REFLECTION_ROUNDS = _as_int(
    cfg("workflow", "max_reflection_rounds"),
    "workflow.max_reflection_rounds",
)
MAX_ORCHESTRATOR_CONCURRENCY = _as_int(
    cfg("workflow", "max_orchestrator_concurrency"),
    "workflow.max_orchestrator_concurrency",
)
MAX_API_CONCURRENT_REVIEWS = _as_int(
    cfg("workflow", "max_api_concurrent_reviews"),
    "workflow.max_api_concurrent_reviews",
)
MODEL_CALL_TIMEOUT_SECONDS = _as_float(
    cfg("workflow", "model_call_timeout_seconds"),
    "workflow.model_call_timeout_seconds",
)
MODEL_CALL_MAX_RETRIES = _as_int(
    cfg("workflow", "model_call_max_retries"),
    "workflow.model_call_max_retries",
)

CHUNK_SIZE = _as_int(cfg("retrieval", "chunk_size"), "retrieval.chunk_size")
CHUNK_OVERLAP = _as_int(cfg("retrieval", "chunk_overlap"), "retrieval.chunk_overlap")
SIMILARITY_TOP_K = _as_int(cfg("retrieval", "similarity_top_k"), "retrieval.similarity_top_k")
RERANK_TOP_N = _as_int(cfg("retrieval", "rerank_top_n"), "retrieval.rerank_top_n")

DATA_DIR = str(PROJECT_ROOT_PATH / "data")
USERS_FILE = str(PROJECT_ROOT_PATH / "user_profiles" / "users.json")

API_KEEP_INPUT = _parse_bool(cfg("api", "keep_input"), "api.keep_input")
API_WRITE_LOGS = _parse_bool(cfg("api", "write_logs"), "api.write_logs")
API_META_REQUIRED = _parse_bool(cfg("api", "meta_required"), "api.meta_required")
API_META_FIELDS = _as_str_tuple(cfg("api", "meta_fields"), "api.meta_fields")
API_CALLBACK_ENABLED = _parse_bool(cfg("api", "callback_enabled"), "api.callback_enabled")
API_CALLBACK_URL = _as_str(cfg("api", "callback_url"), "api.callback_url")
API_CALLBACK_FILE_FIELD = _as_str(
    cfg("api", "callback_file_field"),
    "api.callback_file_field",
) or "file"
API_URL_DOWNLOAD_TIMEOUT_SECONDS = _as_float(
    cfg("api", "url_download_timeout_seconds"),
    "api.url_download_timeout_seconds",
)
API_URL_DOWNLOAD_MAX_BYTES = _as_size_bytes(
    cfg("api", "url_download_max_size"),
    "api.url_download_max_size",
)

DOCX_COMMENT_INCLUDE_CRITERION = _parse_bool(
    cfg("docx", "comment_include_criterion"),
    "docx.comment_include_criterion",
)

ENABLE_WORKFLOW_LOGS = _parse_bool(
    cfg("logging", "enable_workflow_logs"),
    "logging.enable_workflow_logs",
)

print("[config] Retrieval mode : LlamaIndex temporary contract RAG (MCP)")
print(
    f"[config] LLM            : {LLM_NAME}  "
    f"(ctx={MAX_CONTEXT_TOKENS:,}  out={MAX_RESULT_TOKENS:,}  tools={MAX_TOOL_CALLS})"
)
