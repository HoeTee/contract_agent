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
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs", "workflow")

MAX_REFLECTION_ROUNDS = int(os.getenv("MAX_REFLECTION_ROUNDS", "3"))

LLM_NAME = os.getenv("LLM_NAME", "qwen-plus").lower()

_LLM_PROFILES = {
    "qwen-plus": (120_000, 4_000, 25),
    "deepseek-chat": (128_000, 8_000, 40),
    "minimax-k2.5": (240_000, 8_000, 40),
}
MAX_CONTEXT_TOKENS, MAX_RESULT_TOKENS, MAX_TOOL_CALLS = _LLM_PROFILES.get(
    LLM_NAME,
    (100_000, 5_000, 10),
)

print("[config] Retrieval mode : LlamaIndex temporary contract RAG (MCP)")
print(
    f"[config] LLM            : {LLM_NAME}  "
    f"(ctx={MAX_CONTEXT_TOKENS:,}  out={MAX_RESULT_TOKENS:,}  tools={MAX_TOOL_CALLS})"
)
