from __future__ import annotations

from pathlib import Path

from docx_retrieval.detection import find_attachment_parent, find_first_body_start, find_tail_start
from docx_retrieval.detection.patterns import MAIN_SECTION_RE
from docx_retrieval.parser import read_docx_items
from docx_retrieval.schema import DocumentIndex, DocumentNode

from .anchors import build_anchor_map
from .attachments import build_attachments
from .hierarchy import build_hierarchy_for_range, flatten_nodes
from .node_factory import make_node
from .token_budget import (
    NODE_HARD_LIMIT_TOKENS,
    NODE_SOFT_LIMIT_TOKENS,
    NODE_TARGET_TOKENS,
    STRUCTURE_INLINE_BUDGET_TOKENS,
    STRUCTURE_PAGED_BUDGET_TOKENS,
)


def build_document_index(docx_path: Path) -> DocumentIndex:
    items = read_docx_items(docx_path)
    if not items:
        raise ValueError(f"No readable word/document.xml body found: {docx_path}")

    body_start = find_first_body_start(items)
    attachment_parent = find_attachment_parent(items, body_start)
    body_end = attachment_parent if attachment_parent is not None else len(items)
    tail_start = find_tail_start(items, body_start, body_end)
    body_content_end = tail_start if tail_start is not None else body_end

    use_cn_as_l1 = not any(item.kind == "p" and MAIN_SECTION_RE.match(item.text) for item in items[body_start:body_content_end])
    roots: list[DocumentNode] = []

    frontmatter = make_node("frontmatter", "frontmatter", "合同首部", items, 0, max(body_start, 1), 0, None)
    body = make_node("body", "body", "正文", items, body_start, max(body_content_end, body_start + 1), 0, None)
    body.children = build_hierarchy_for_range(items, body_start, body_content_end, "body", "body", use_cn_as_l1)
    roots.extend([frontmatter, body])

    if tail_start is not None and tail_start < body_end:
        roots.append(make_node("tail", "tail", "合同末尾", items, tail_start, body_end, 0, None))
    else:
        roots.append(DocumentNode(node_id="tail", node_type="tail", title="合同末尾", start_anchor="", end_anchor="", level=0))

    attachments = DocumentNode(node_id="attachments", node_type="attachments", title="附件", start_anchor="", end_anchor="", level=0)
    if attachment_parent is not None:
        attachment_parent_node = make_node(
            "attachments/parent",
            "attachment_parent",
            items[attachment_parent].text,
            items,
            attachment_parent,
            len(items),
            1,
            "attachments",
        )
        attachment_parent_node.children = build_attachments(items, attachment_parent + 1, len(items), attachment_parent_node.node_id)
        attachments.children.append(attachment_parent_node)
    roots.append(attachments)

    flat_nodes = flatten_nodes(roots)
    return DocumentIndex(
        source_file=str(docx_path),
        top_regions={
            "frontmatter": "frontmatter",
            "body": "body",
            "tail": "tail",
            "attachments": "attachments",
        },
        settings={
            "node_target_tokens": NODE_TARGET_TOKENS,
            "node_soft_limit_tokens": NODE_SOFT_LIMIT_TOKENS,
            "node_hard_limit_tokens": NODE_HARD_LIMIT_TOKENS,
            "summary_tree_inline_budget_tokens": STRUCTURE_INLINE_BUDGET_TOKENS,
            "summary_tree_paged_budget_tokens": STRUCTURE_PAGED_BUDGET_TOKENS,
        },
        nodes=[node.storage_view() for node in flat_nodes],
        root_nodes=[node.node_id for node in roots],
        structure_tree=[node.structure_view() for node in roots],
        anchor_map=build_anchor_map(items, flat_nodes),
    )
