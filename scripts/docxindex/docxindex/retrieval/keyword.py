from __future__ import annotations

from typing import Any

from docxindex.schema import RetrievalMatch, RetrievalResult


def keyword_search(index: dict[str, Any], keywords: list[str]) -> RetrievalResult:
    matches: list[RetrievalMatch] = []
    for keyword in keywords:
        for node in index["nodes"]:
            title = node.get("title") or ""
            text = node.get("text") or ""
            has_children = bool(node.get("nodes") or node.get("children"))
            if keyword in title:
                matches.append(
                    RetrievalMatch(
                        keyword=keyword,
                        match_type="title",
                        match_text=title,
                        node_id=node["node_id"],
                        anchor=node.get("start_anchor"),
                    )
                )
            elif not has_children and keyword in text:
                pos = text.find(keyword)
                matches.append(
                    RetrievalMatch(
                        keyword=keyword,
                        match_type="text",
                        match_text=text[max(0, pos - 30) : pos + len(keyword) + 30],
                        node_id=node["node_id"],
                        anchor=node.get("start_anchor"),
                    )
                )
    return RetrievalResult(matches=matches)
