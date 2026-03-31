"""
Central configuration for the contract review workflow.
All paths and constants defined here — single source of truth.
"""
import os
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH)

# ── Paths ──────────────────────────────────────────────────
MCP_SERVER_PATH = os.path.join(PROJECT_ROOT, "mcp_service", "mcp_server", "mcp_server.py")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs", "workflow")

# ── Retrieval mode ─────────────────────────────────────────
# LLAMA_INDEX=True  → LlamaIndex RAG via MCP (PAGEINDEX_SEARCH is ignored)
# LLAMA_INDEX=False + PAGEINDEX_SEARCH=True  → PageIndex tree search via MCP
# LLAMA_INDEX=False + PAGEINDEX_SEARCH=False → EvidenceCollector agent
LLAMA_INDEX = os.getenv("LLAMA_INDEX", "False").lower() in ("true", "1", "yes")
PAGEINDEX_SEARCH = os.getenv("PAGEINDEX_SEARCH", "True").lower() in ("true", "1", "yes")

RETRIEVAL_MODE_LABELS = {
    "llamaindex": "LlamaIndex RAG (MCP)",
    "pageindex": "PageIndex tree search (MCP)",
    "evidence": "EvidenceCollector agent",
}


def get_default_retrieval_mode() -> str:
    """Return the default retrieval mode derived from environment flags."""
    if LLAMA_INDEX:
        return "llamaindex"
    if PAGEINDEX_SEARCH:
        return "pageindex"
    return "evidence"


def get_retrieval_mode(mode: str | None = None) -> str:
    """Return a human-readable label for the active retrieval strategy."""
    return RETRIEVAL_MODE_LABELS.get(
        mode,
        RETRIEVAL_MODE_LABELS[get_default_retrieval_mode()]
    )

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
print(f"[config] LLM            : {LLM_NAME}  (ctx={MAX_CONTEXT_TOKENS:,}  out={MAX_RESULT_TOKENS:,}  tools={MAX_TOOL_CALLS})")
