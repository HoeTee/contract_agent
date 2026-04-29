"""
Central configuration for the contract review workflow.
All paths and constants defined here — single source of truth.

All environment variables are validated at import time. Invalid values raise
``ConfigError`` immediately so misconfiguration cannot silently degrade behavior.
"""
import os
from dotenv import load_dotenv

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH)


class ConfigError(ValueError):
    """Raised when an environment variable holds an unsupported value."""


_TRUE_LITERALS = {"true", "1", "yes", "on"}
_FALSE_LITERALS = {"false", "0", "no", "off"}


def _env_bool(name: str, default: bool = False) -> bool:
    """Strictly parse a boolean env variable. Anything outside the allowed
    literals raises ``ConfigError`` so typos like ``Ture`` or ``flase`` fail fast.
    """
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUE_LITERALS:
        return True
    if normalized in _FALSE_LITERALS:
        return False
    allowed = sorted(_TRUE_LITERALS | _FALSE_LITERALS)
    raise ConfigError(
        f"{name}={raw!r} is not a valid boolean. Allowed values: {allowed}"
    )


def _env_choice(name: str, allowed: set[str], default: str) -> str:
    """Read an env variable that must match one of the ``allowed`` values."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value not in allowed:
        raise ConfigError(
            f"{name}={raw!r} is not a valid choice. Allowed values: {sorted(allowed)}"
        )
    return value


def _env_int(name: str, default: int, *, min_value: int | None = None) -> int:
    """Read an integer env variable with optional lower-bound validation."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid integer.") from exc
    if min_value is not None and value < min_value:
        raise ConfigError(
            f"{name}={value} is below the minimum allowed value {min_value}."
        )
    return value


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
RETRIEVAL_MODE_LABELS = {
    "llamaindex": "LlamaIndex RAG (MCP)",
    "pageindex": "PageIndex tree search (MCP)",
    "evidence": "EvidenceCollector agent",
}

def get_default_retrieval_mode() -> str:
    """Return the default retrieval mode derived from environment flags."""
    if _env_bool("LLAMA_INDEX", default=False):
        return "llamaindex"
    if _env_bool("PAGEINDEX_SEARCH", default=True):
        return "pageindex"
    return "evidence"

def get_retrieval_mode(mode: str | None = None) -> str:
    """Return a human-readable label for the active retrieval strategy."""
    if mode is None:
        mode = get_default_retrieval_mode()
    if mode not in RETRIEVAL_MODE_LABELS:
        raise ConfigError(
            f"retrieval mode {mode!r} is not supported. "
            f"Allowed values: {sorted(RETRIEVAL_MODE_LABELS)}"
        )
    return RETRIEVAL_MODE_LABELS[mode]


# ── Online search ─────────────────────────────────────────
def get_default_web_search_enabled() -> bool:
    """Return the task-level web-search flag from the environment."""
    return _env_bool("ENABLE_MCP_WEB_TOOLS", default=False)


# ── Agent config ───────────────────────────────────────────
MAX_REFLECTION_ROUNDS = _env_int("MAX_REFLECTION_ROUNDS", default=3, min_value=0)


# ── LLM config ────────────────────────────────────────────
# LLM_NAME is intentionally free-form (model identifiers vary across providers).
# Unknown names fall back to a conservative token budget; a warning is emitted
# so you know to add a profile entry for accurate context budgeting.
_LLM_PROFILES = {
    "qwen-plus":    (120_000, 4_000,  25),
    "deepseek-chat": (128_000, 8_000, 40),
    "minimax-k2.5": (240_000, 8_000,  40),
}
_DEFAULT_LLM_PROFILE = (100_000, 5_000, 10)
LLM_NAME = os.getenv("LLM_NAME", "qwen-plus").strip().lower()
if LLM_NAME in _LLM_PROFILES:
    MAX_CONTEXT_TOKENS, MAX_RESULT_TOKENS, MAX_TOOL_CALLS = _LLM_PROFILES[LLM_NAME]
else:
    print(
        f"[config] WARNING: LLM_NAME={LLM_NAME!r} has no profile entry; "
        f"falling back to default budget {_DEFAULT_LLM_PROFILE}. "
        f"Add it to _LLM_PROFILES in config.py for accurate limits."
    )
    MAX_CONTEXT_TOKENS, MAX_RESULT_TOKENS, MAX_TOOL_CALLS = _DEFAULT_LLM_PROFILE


# ── Eager validation of remaining env booleans ────────────
# Trigger parsing so a bad value fails at import time, not on first use.
get_default_retrieval_mode()
get_default_web_search_enabled()
_env_bool("PARSE_FILE_WITH_MINERU", default=False)
_env_bool("ONLINE_SEARCH", default=False)


# ── Startup banner ─────────────────────────────────────────
print(f"[config] Default retrieval mode : {get_retrieval_mode()}")
print(f"[config] LLM            : {LLM_NAME}  (ctx={MAX_CONTEXT_TOKENS:,}  out={MAX_RESULT_TOKENS:,}  tools={MAX_TOOL_CALLS})")
