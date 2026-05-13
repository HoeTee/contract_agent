from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from tools.retrieval.index_retriever import IndexRetriever


async def main() -> int:
    print("Building institutional index...")
    print(f"Project root: {PROJECT_ROOT}")
    retriever = IndexRetriever(
        project_root=PROJECT_ROOT,
        llm_api_key=os.getenv("LLM_API_KEY"),
        llm_base_url=os.getenv("LLM_BASE_URL"),
        llm_name=os.getenv("LLM_NAME", "qwen-plus"),
        embed_api_key=os.getenv("EMBED_API_KEY", os.getenv("LLM_API_KEY")),
        embed_base_url=os.getenv("EMBED_BASE_URL", os.getenv("LLM_BASE_URL")),
        embed_name=os.getenv("EMBED_NAME", "text-embedding-v4"),
        rerank_api_key=os.getenv("RERANK_API_KEY"),
        rerank_base_url=os.getenv("RERANK_BASE_URL"),
        rerank_name=os.getenv("RERANK_NAME"),
    )
    print(f"Institutional docs: {retriever.institutional_docs_dir}")
    print(f"Index path: {retriever.institutional_index_dir}")
    print(f"Manifest path: {retriever.institutional_manifest_path}")
    result = await retriever.build_institutional_index()
    print("Institutional index update result:")
    print(json.dumps(json.loads(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
