import os
import json
import argparse
from pathlib import Path
from typing import Callable
import sys
import re
import asyncio
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.base_agent import Agent
from agents.json_utils import chat_until_valid_json
from agents.schemas import SubAgentOutput
from agents.prompts.cn_prompts import SUB_AGENT_BASE_PROMPT
from config import MCP_SERVER_PATH
from workflow.client_loader import MinimalMCPClient

SUB_AGENT_EXPECTED_JSON = """
{
  "status": "compliant 或 issues_found",
  "issues": [
    {
      "issue_id": "当前criterion_id.序号",
      "risk_level": "high | medium | low",
      "quoted_text": "逐字摘录的合同原文；合同未出现对应内容时为空字符串",
      "comment_text": "可直接写入 Word 批注的修改意见，100字以内"
    }
  ]
}
"""

criterion_path = r"C:\Users\18014\OneDrive\Desktop\开发网程序打包\开发网程序文件打包_2\deep_research_agent\scripts\planner_result.json"
criterion = json.loads(Path(criterion_path).read_text(encoding="utf-8"))["criteria"][3]


def build_parser() -> argparse.ArgumentParser: 
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    return parser

def strip_ingest_header(text: str) -> str:
    marker = "Content:\n\n"
    if marker in text:
        return text.split(marker, 1)[1]
    return text


async def contract(
    client, 
    file_path: Path
) -> str:
    await client.call_tool(
        "ingest_file",
        {"file_path": str(file_path)},
    )
    await client.call_tool(
        "llamaindex_build_index", 
        {"docx_path": str(file_path)}
    )


def _prepare_review_context(
    context: str
) -> str:
    """Add guardrails so retrieval wrapper text is not mistaken for contract locations."""
    normalized_context = context or "未找到相关内容。"
    normalized_context = re.sub(
        r"^##\s*检索结果\s*\d+(?:\s*\([^)]*\))?\s*$",
        "",
        normalized_context,
        flags=re.MULTILINE,
    )
    normalized_context = re.sub(r"\n{3,}", "\n\n", normalized_context).strip()
    guidance = (
        '注意：下面内容中的”检索结果1/2””相关度分数””检索片段标题”等仅是检索系统包装信息，'
        '不是合同原始条款标题或所在位置。输出”所在位置”时只能填写合同原文中真实出现的条款、'
        '章节或段落位置；若合同原文未标明具体条款编号，请写”合同缺失审查要点要求书写的内容”，'
        '绝对不要照抄检索包装标题。'
    )
    return f"{guidance}\n\n{normalized_context}"


async def _retrieve_context(
    file_path: str, 
    client: Callable, 
    criterion_text: str,
    check_points_text: str
) -> tuple[str, int]:
    """Unified retrieval: returns (context_text, retrieval_tokens)."""
    await contract(client, file_path)
    
    search_query = f"{criterion_text}\n检查要点：{check_points_text}"
    search_result = await client.call_tool(
        "llamaindex_search",
        {"query": search_query}
    )
    if isinstance(search_result, str) and search_result.startswith("Error"):
        raise RuntimeError(search_result)
    context = search_result if search_result else "未找到相关内容。"

    return _prepare_review_context(context)


async def resp(
    criterion: str, 
    file_path: str
) -> str: 

    client = MinimalMCPClient(server_script_path=MCP_SERVER_PATH)
    await client.connect()
    tools = await client.get_available_tools()

    sub_agent = Agent(
        system_prompt=SUB_AGENT_BASE_PROMPT,
        name=f"SubAgent",
        mcp_client=client,
        tools=tools
    )

    criterion_text = criterion["criterion"]
    check_points = criterion["check_points"]
    check_points_text = "\n".join(f"- {cp}" for cp in check_points)
    context = await _retrieve_context(
        file_path, 
        client, 
        criterion_text, 
        check_points_text
    )

    task_prompt = (
    f"审查标准：{criterion_text}\n"
    f"检查要点：\n{check_points_text}\n\n"
    f"以下是合同原文中与此标准相关的内容：\n\n{context}\n\n"
    )

    parsed, _ = await chat_until_valid_json(
        sub_agent,
        task_prompt,
        SubAgentOutput,
        SUB_AGENT_EXPECTED_JSON,
    )
    await client.cleanup()

    output_path = PROJECT_ROOT / "scripts/subagent_result.json"
    Path(output_path).write_text(
        json.dumps(parsed), 
        encoding="utf-8"
    )

    return parsed


async def main(): 
    args = build_parser().parse_args()
    file_path = Path(args.file).expanduser().resolve()

    if not file_path.exists():
        raise FileNotFoundError(f"File does not exist: {file_path}")
    
    subagent_op = await resp(
        criterion, 
        file_path
    )
    return subagent_op


if __name__ == "__main__": 
      print(asyncio.run(main()))
