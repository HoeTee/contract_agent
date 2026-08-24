from __future__ import annotations

import re
from typing import Any

from tools.docxindex.llm.schemas import RouteStep

from .region import _unique
from .rule import _scan_nodes
from .title import _candidate


WORD = re.compile(r"[\u4e00-\u9fff]{2,8}")


def join_matches(index: dict[str, Any], query: str, step: RouteStep) -> list[dict[str, Any]]:
    nodes = index.get("nodes") or []
    by_id = {node.get("node_id"): node for node in nodes}
    result = []
    for region in step.regions:
        node_id = (index.get("top_regions") or {}).get(region, region)
        if node_id in by_id:
            result.append(_candidate(by_id[node_id], "join"))

    words = set(step.terms)
    for slot in step.slots:
        words.update(WORD.findall(slot))
    words.update(_query_terms(query))
    for node in _scan_nodes(index):
        haystack = f"{node.get('title') or ''}\n{node.get('summary') or ''}\n{node.get('text') or ''}"
        if any(word in haystack for word in words):
            result.append(_candidate(node, "join"))
    return _unique(result)


def _query_terms(query: str) -> set[str]:
    preferred = {
        "合同期限", "履行期限", "有效期", "服务期", "签订日期", "项目负责人",
        "支付方式", "合同金额", "付款", "发票", "维保", "保修",
        "甲方", "乙方", "附件", "签署", "以下无正文",
    }
    result = {term for term in preferred if term in query}
    if "金额" in query and any(term in query for term in ("大小写", "大写", "小写", "一致")):
        result.update({"金额", "人民币", "元整", "¥", "大写", "小写", "含税价", "合计"})
    return result
