"""
Central configuration for the contract review workflow.
All paths and constants defined here — single source of truth.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# Paths
MCP_SERVER_PATH = os.path.join(PROJECT_ROOT, "mcp_service", "mcp_server", "mcp_server.py")
DOCS_DIR = os.path.join(PROJECT_ROOT, "docs")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs", "workflow")
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

# Agent config
MAX_REFLECTION_ROUNDS = 3    # ← Change this to adjust reflection loop limit
MAX_TOOL_CALLS = 10

# Load .env to get LLM_NAME
from dotenv import load_dotenv
load_dotenv(ENV_PATH)

llm_name = os.getenv("LLM_NAME", "qwen-plus").lower()

if "qwen-plus" in llm_name:
    MAX_CONTEXT_TOKENS = 1_000_000
elif "qwen-max" in llm_name:
    MAX_CONTEXT_TOKENS = 262_144
elif "deepseek" in llm_name:
    MAX_CONTEXT_TOKENS = 128_000
elif "minimax" in llm_name:
    MAX_CONTEXT_TOKENS = 1_000_000
else:
    MAX_CONTEXT_TOKENS = 100_000  # Default fallback

MAX_RESULT_TOKENS = 5_000
