from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_client_module() -> ModuleType:
    module_path = Path(__file__).resolve().parents[1] / "mcp" / "client" / "mcp_minimal.py"
    spec = importlib.util.spec_from_file_location("_contract_agent_mcp_client", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load MCP client module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MinimalMCPClient = _load_client_module().MinimalMCPClient
