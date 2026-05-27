from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config import MCP_SERVER_PATH
from mcp_service.mcp_client.mcp_minimal import MinimalMCPClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call the MCP ingest_file tool directly for one document."
    )
    parser.add_argument(
        "file_path",
        help="DOCX/PDF/TXT file path to ingest. Relative paths are resolved from the current directory.",
    )
    parser.add_argument(
        "--server",
        default=MCP_SERVER_PATH,
        help="MCP server script path or HTTP URL. Defaults to this project's MCP server.",
    )
    parser.add_argument(
        "--output",
        help="Optional path for writing the ingested markdown content.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print/write the raw MCP tool response instead of stripping the response header.",
    )
    return parser


def strip_ingest_header(tool_result: str) -> str:
    marker = "Content:\n\n"
    if marker not in tool_result:
        return tool_result
    return tool_result.split(marker, 1)[1]


async def ingest_file(file_path: Path, server: str, raw: bool) -> str:
    client = MinimalMCPClient(server)
    await client.connect()
    try:
        result = await client.call_tool(
            "ingest_file",
            {
                "file_path": str(file_path),
            },
        )
    finally:
        await client.cleanup()

    return result if raw else strip_ingest_header(result)


async def main_async() -> None:
    args = build_parser().parse_args()
    file_path = Path(args.file_path).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Input file was not found: {file_path}")

    content = await ingest_file(file_path, args.server, args.raw)

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        print(f"Wrote ingested content to: {output_path}")
        return

    print(content)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
