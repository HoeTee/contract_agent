"""
Central configuration for the contract review workflow.
All paths and constants defined here — single source of truth.
"""
import os
from dotenv import load_dotenv
from offline_bootstrap import configure_offline_tiktoken

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
configure_offline_tiktoken(PROJECT_ROOT)
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH)


def _env_bool(value: str | None, default: bool = False) -> bool:
    """Parse a common boolean environment variable representation."""
    if value is None:
        return default
    return str(value).lower() in ("true", "1", "yes", "on")

# ── Paths ──────────────────────────────────────────────────
MCP_SERVER_PATH = os.path.join(PROJECT_ROOT, "mcp_service", "mcp_server", "mcp_server.py")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs", "workflow")

# ── Retrieval mode ─────────────────────────────────────────
# CONTRACT_RETRIEVAL_MODE=pageindex   → PageIndex tree search via MCP
# CONTRACT_RETRIEVAL_MODE=llamaindex  → temporary in-memory LlamaIndex contract RAG
# CONTRACT_RETRIEVAL_MODE=evidence    → EvidenceCollector agent
CONTRACT_RETRIEVAL_MODE = os.getenv("CONTRACT_RETRIEVAL_MODE")
ENABLE_INSTITUTIONAL_RAG = _env_bool(os.getenv("ENABLE_INSTITUTIONAL_RAG"), default=False)
INSTITUTIONAL_DOCS_DIR = os.getenv("INSTITUTIONAL_DOCS_DIR", os.path.join("docs", "institutional_docs"))

RETRIEVAL_MODE_LABELS = {
    "pageindex": "PageIndex tree search (MCP)",
    "llamaindex": "LlamaIndex temporary contract RAG (MCP)",
    "evidence": "EvidenceCollector agent",
}


def get_default_retrieval_mode() -> str:
    """Return the explicitly configured contract retrieval mode."""
    if not CONTRACT_RETRIEVAL_MODE:
        raise ValueError("CONTRACT_RETRIEVAL_MODE must be set to pageindex, llamaindex, or evidence.")
    if CONTRACT_RETRIEVAL_MODE not in RETRIEVAL_MODE_LABELS:
        raise ValueError("CONTRACT_RETRIEVAL_MODE must be one of: pageindex, llamaindex, evidence.")
    return CONTRACT_RETRIEVAL_MODE


def get_default_institutional_rag_enabled() -> bool:
    """Return whether institutional-document retrieval is enabled."""
    return ENABLE_INSTITUTIONAL_RAG


def get_retrieval_mode(mode: str | None = None) -> str:
    """Return a human-readable label for the active retrieval strategy."""
    selected_mode = mode or get_default_retrieval_mode()
    if selected_mode not in RETRIEVAL_MODE_LABELS:
        raise ValueError("retrieval mode must be one of: pageindex, llamaindex, evidence.")
    return RETRIEVAL_MODE_LABELS[selected_mode]


def get_default_web_search_enabled() -> bool:
    """Return the default task-level web search flag from the environment."""
    raw_value = os.getenv("ENABLE_WEB_SEACH_TOOL")
    if raw_value is None:
        raw_value = os.getenv("ENABLE_MCP_WEB_TOOLS")
    return _env_bool(raw_value, default=False)

# ── Agent config ───────────────────────────────────────────
MAX_REFLECTION_ROUNDS = int(os.getenv("MAX_REFLECTION_ROUNDS", "3"))

# ── LLM config ────────────────────────────────────────────
LLM_NAME = os.getenv("LLM_NAME", "qwen-plus").lower()

_LLM_PROFILES = {
    "qwen-plus":    (120_000, 4_000,  25),
    "deepseek-chat": (128_000, 8_000, 40),
    "minimax-k2.5": (240_000, 8_000,  40),
}
MAX_CONTEXT_TOKENS, MAX_RESULT_TOKENS, MAX_TOOL_CALLS = _LLM_PROFILES.get(
    LLM_NAME, (100_000, 5_000, 10)
)

# ── Startup banner ─────────────────────────────────────────
print(f"[config] Default retrieval mode : {get_retrieval_mode(get_default_retrieval_mode())}")
print(f"[config] Institutional RAG     : {ENABLE_INSTITUTIONAL_RAG}")
print(f"[config] LLM            : {LLM_NAME}  (ctx={MAX_CONTEXT_TOKENS:,}  out={MAX_RESULT_TOKENS:,}  tools={MAX_TOOL_CALLS})")
