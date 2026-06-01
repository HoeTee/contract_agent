"""
Central configuration for the contract review workflow.
"""

import os

from dotenv import load_dotenv


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
load_dotenv(ENV_PATH)

MCP_SERVER_PATH = os.path.join(PROJECT_ROOT, "mcp_service", "mcp_server", "mcp_server.py")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")

DATA_DIR = os.getenv("DATA_DIR", os.path.join(PROJECT_ROOT, "data"))
if not os.path.isabs(DATA_DIR):
    DATA_DIR = os.path.join(PROJECT_ROOT, DATA_DIR)

DEFAULT_REVIEW_CRITERIA_PATH = os.path.join(PROJECT_ROOT, "resources", "review_criteria", "criteria.docx")

USERS_FILE = os.getenv("USERS_FILE", os.path.join(PROJECT_ROOT, "user_profiles", "users.json"))
if not os.path.isabs(USERS_FILE):
    USERS_FILE = os.path.join(PROJECT_ROOT, USERS_FILE)

DEFAULT_CLI_USERNAME = os.getenv("DEFAULT_CLI_USERNAME", "default")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "change-this-session-secret")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs", "workflow")

def _required_env_bool(name: str) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        raise RuntimeError(f"{name} is required. Set it to true or false in .env.")

    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false, got {raw!r}.")


ENABLE_WORKFLOW_LOGS = _required_env_bool("ENABLE_WORKFLOW_LOGS")

MAX_REFLECTION_ROUNDS = int(os.getenv("MAX_REFLECTION_ROUNDS", "3"))
MAX_ORCHESTRATOR_CONCURRENCY = int(os.getenv("MAX_ORCHESTRATOR_CONCURRENCY", "8"))
MAX_API_CONCURRENT_REVIEWS = int(os.getenv("MAX_API_CONCURRENT_REVIEWS", "1"))

LLM_NAME = os.getenv("LLM_NAME", "qwen-plus").lower()

_LLM_PROFILES = {
    "qwen-plus": (120_000, 4_000, 25),
    "deepseek-chat": (128_000, 8_000, 40),
    "minimax-k2.5": (240_000, 8_000, 40),
}
MAX_CONTEXT_TOKENS, MAX_RESULT_TOKENS, MAX_TOOL_CALLS = _LLM_PROFILES.get(
    LLM_NAME,
    (128_000, 5_000, 10),
)

print("[config] Retrieval mode : LlamaIndex temporary contract RAG (MCP)")
print(
    f"[config] LLM            : {LLM_NAME}  "
    f"(ctx={MAX_CONTEXT_TOKENS:,}  out={MAX_RESULT_TOKENS:,}  tools={MAX_TOOL_CALLS})"
)
