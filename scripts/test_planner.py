from __future__ import annotations

import argparse
import asyncio
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.planner import PlannerAgent
from config import MCP_SERVER_PATH
from mcp_service.mcp_client.mcp_minimal import MinimalMCPClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="Path to the DOCX/PDF/TXT file to ingest and plan.")
    return parser


def strip_ingest_header(text: str) -> str:
    marker = "Content:\n\n"
    if marker in text:
        return text.split(marker, 1)[1]
    return text


async def ingest(file_path: Path) -> str:
    client = MinimalMCPClient(server_script_path=MCP_SERVER_PATH)
    await client.connect()
    try:
        result = await client.call_tool(
            "ingest_file",
            {"file_path": str(file_path)},
        )
    finally:
        await client.cleanup()
    return result


async def plan() -> dict:
    args = build_parser().parse_args()
    file_path = Path(args.file).expanduser().resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {file_path}")

    content = strip_ingest_header(await ingest(file_path))
    planner = PlannerAgent()
    result = await planner.design_tasks(content)
    output_path = PROJECT_ROOT / "scripts/planner_result.json"
    Path(output_path).write_text(
        json.dumps(result), 
        encoding="utf-8"
    )
    return result


if __name__ == "__main__":
    print(asyncio.run(plan()))
