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

# Search mode: True = use PageIndex search, False = use Evidence Collector
PAGEINDEX_SEARCH = os.getenv("PAGEINDEX_SEARCH", "True").lower() in ("true", "1", "yes")

# Load .env to get LLM_NAME
from dotenv import load_dotenv
load_dotenv(ENV_PATH)

LLM_NAME = os.getenv("LLM_NAME", "qwen-plus").lower()

if LLM_NAME == "qwen-plus":
    MAX_CONTEXT_TOKENS = 120_000
    MAX_RESULT_TOKENS = 4_000
    MAX_TOOL_CALLS = 25

elif LLM_NAME == "deepseek-chat":
    MAX_CONTEXT_TOKENS = 128_000
    MAX_RESULT_TOKENS = 8_000
    MAX_TOOL_CALLS = 40

elif LLM_NAME == "minimax-k2.5":
    MAX_CONTEXT_TOKENS = 240_000
    MAX_RESULT_TOKENS = 8_000
    MAX_TOOL_CALLS = 40
else: # Default fallback
    MAX_CONTEXT_TOKENS = 100_000  
    MAX_RESULT_TOKENS = 5_000
    MAX_TOOL_CALLS = 10
