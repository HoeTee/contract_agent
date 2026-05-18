"""
AgentLogger — handles per-agent conversation logging to JSON files.
Saves full LLM I/O (system prompt, user messages, assistant responses, tool calls)
to logs/conversations/<run_timestamp>/ for debugging and auditing.

Each run of main.py creates a separate timestamped folder so logs from
different runs don't mix together.
"""
import json
import os
from datetime import datetime

from config import ENABLE_WORKFLOW_LOGS

# Project root for log paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Create a unique session folder for this run (set once at import time)
_SESSION_TS = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
SESSION_DIR = os.path.join(PROJECT_ROOT, "logs", "conversations", f"run_{_SESSION_TS}")


def _serialize_messages(messages: list) -> list:
    """Convert conversation messages to JSON-serializable format."""
    serializable = []
    for msg in messages:
        try:
            role = msg.get("role")
            out = {"role": role}

            if "content" in msg:
                c = msg["content"]
                out["content"] = c if (c is None or isinstance(c, str)) else str(c)

            if role == "assistant" and "tool_calls" in msg:
                tool_calls = msg["tool_calls"] or []
                out_tcs = []
                for tc in tool_calls:
                    if hasattr(tc, "model_dump"):
                        tc = tc.model_dump()
                    elif hasattr(tc, "to_dict"):
                        tc = tc.to_dict()
                    out_tcs.append({
                        "id": tc.get("id"),
                        "type": tc.get("type", "function"),
                        "function": {
                            "name": (tc.get("function") or {}).get("name"),
                            "arguments": (tc.get("function") or {}).get("arguments"),
                        },
                    })
                out["tool_calls"] = out_tcs

            if role == "tool":
                out["tool_call_id"] = msg.get("tool_call_id")

            serializable.append(out)
        except Exception as e:
            print(f"Error processing message: {e}")

    return serializable


def log_conversation(agent_name: str, messages: list) -> None:
    """
    Save agent conversation to a JSON file in the current run's folder.

    Args:
        agent_name: Name of the agent (used in filename).
        messages: List of conversation messages.
    """
    if not ENABLE_WORKFLOW_LOGS:
        return

    os.makedirs(SESSION_DIR, exist_ok=True)

    serializable = _serialize_messages(messages)

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filepath = os.path.join(SESSION_DIR, f"{agent_name}_{ts}.json")
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error writing conversation log: {e}")
