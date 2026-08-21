from __future__ import annotations

import json
import re
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from pydantic import BaseModel, ConfigDict, Field

from docxindex.llm import LLMClient
from docxindex.llm.cache import JsonlCache, cache_key, text_hash
from docxindex.llm.schemas import RouteResponse
from docxindex.llm.config import load_yaml


DEFAULT_ROUTE_CONFIG = Path(__file__).resolve().parents[2] / "config.yaml"
ROUTE_PROMPT_VERSION = "docx_route_v1"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NUMBERED_CRITERION = re.compile(r"^\s*(\d{1,2})(?:\s*[.、．]\s*|\s+)(.+)$", re.S)


class RouteConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: Path
    expected_criteria_count: int = Field(default=18, ge=1)
    fallback_enabled: bool = True
    methods: dict[str, str]
    llm_candidates: int = Field(default=12, ge=1)
    vector_candidates: int = Field(default=20, ge=1)
    vector_threshold: float = Field(default=0.45, ge=0.0, le=1.0)
    max_nodes: int = Field(default=5, ge=1)

    @classmethod
    def load(cls, path: Path | None = None) -> "RouteConfig":
        config_path = (path or DEFAULT_ROUTE_CONFIG).resolve()
        raw = load_yaml(config_path)
        data = dict(raw.get("routing") or {})
        source = Path(str(data.get("criteria") or ""))
        if not source.is_absolute():
            source = (config_path.parent / source).resolve()
        data["criteria"] = source
        config = cls.model_validate(data)
        if set(config.methods) != {"title", "region", "rule", "join", "scan"}:
            raise ValueError("route methods must be exactly: title, region, rule, join, scan")
        return config


def plan_route(
    index: dict[str, Any],
    query: str,
    client: LLMClient,
    config: RouteConfig,
    cache_dir: Path | None,
) -> RouteResponse:
    criteria = load_criteria(config.criteria, config.expected_criteria_count)
    criterion = _criterion_for_query(query, criteria)
    titles = _titles(index.get("structure_tree") or [])
    prompt = _prompt(query, criterion, titles, config)
    cache = JsonlCache(cache_dir / "route.jsonl" if cache_dir else None)
    key = cache_key(
        ROUTE_PROMPT_VERSION,
        client.settings.model,
        query,
        text_hash(criterion),
        text_hash(json.dumps(config.methods, ensure_ascii=False, sort_keys=True)),
        text_hash("\n".join(titles)),
    )
    cached = cache.get(key)
    if cached is None:
        response = client.complete_model(prompt, RouteResponse)
        cached = response.model_dump(mode="json")
        cache.set(key, cached)
    return RouteResponse.model_validate(cached)


@lru_cache(maxsize=8)
def _cached_criteria(path_text: str, modified_ns: int, expected_count: int) -> dict[int, str]:
    del modified_ns
    path = Path(path_text)
    with zipfile.ZipFile(path) as package:
        root = ET.fromstring(package.read("word/document.xml"))
    paragraphs = []
    for paragraph in root.findall(f".//{{{W_NS}}}body/{{{W_NS}}}p"):
        text_parts = []
        for text_node in paragraph.iter(f"{{{W_NS}}}t"):
            if any(ancestor.tag == f"{{{W_NS}}}del" for ancestor in _ancestors(paragraph, text_node)):
                continue
            text_parts.append(text_node.text or "")
        text = "".join(text_parts).strip()
        if text:
            paragraphs.append(text)
    result = {}
    for text in paragraphs:
        match = NUMBERED_CRITERION.match(text)
        if match and 1 <= int(match.group(1)) <= expected_count:
            result[int(match.group(1))] = f"{match.group(1)}. {match.group(2).strip()}"
    if sorted(result) != list(range(1, expected_count + 1)):
        raise ValueError(f"criteria DOCX must contain numbered criteria 1..{expected_count}: {path}")
    return result


def load_criteria(path: Path, expected_count: int) -> dict[int, str]:
    resolved = path.resolve()
    return _cached_criteria(str(resolved), resolved.stat().st_mtime_ns, expected_count)


def _ancestors(root: ET.Element, target: ET.Element) -> list[ET.Element]:
    parents = {child: parent for parent in root.iter() for child in parent}
    result = []
    current = target
    while current in parents:
        current = parents[current]
        result.append(current)
    return result


def _criterion_for_query(query: str, criteria: dict[int, str]) -> str:
    match = re.match(r"^\s*(\d{1,2})(?:\s*[.、．]\s*|\s+)", query)
    return criteria.get(int(match.group(1)), query) if match else query


def _titles(nodes: list[dict[str, Any]]) -> list[str]:
    result = []
    for node in nodes:
        title = str(node.get("title") or "").strip()
        node_type = str(node.get("node_type") or "")
        if title and node_type not in {"body", "attachments"}:
            result.append(title)
        result.extend(_titles(node.get("nodes") or node.get("children") or []))
    return result[:300]


def _prompt(query: str, criterion: str, titles: list[str], config: RouteConfig) -> str:
    methods = "\n".join(f"- {name}: {description}" for name, description in config.methods.items())
    return f"""你是 DOCX 合同检索路由器，只规划检索方法，不审查合同，不选择 node_id。

用户查询：
{query}

审查要点原文：
{criterion}

当前合同标题目录：
{json.dumps(titles, ensure_ascii=False)}

可用方法：
{methods}

规划规则：
- 可以组合多个步骤，但避免重复扫描。
- 标题是否存在、标题顺序、目录检查使用 title；需要完整目录时 all_titles=true。
- 明确固定区域或明确标题下内容使用 region；region 可取 frontmatter/body/tail/attachments。
- 精确关键词、金额、存在或不存在判断使用 rule，并在 terms 中列出需要原文匹配的短词。
- 两个以上区域、首尾、正文与附件或多个证据角色需要联合判断时使用 join，并在 slots 中列出证据角色。
- 错别字、语病或必须逐段通读全文的问题使用 scan，且不再组合其他步骤。
- 只有确定性步骤不足以定位语义证据时 fallback=true。
- 不得把审查结论写进检索计划。

只返回符合 schema 的 JSON object。"""
