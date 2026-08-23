from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from typing import Any

from docxindex.detection import find_attachment_parent, find_first_body_start, find_tail_start
from docxindex.detection.patterns import MAIN_SECTION_RE
from docxindex.llm import LLMClient, LLMSettings
from docxindex.parser import read_docx_items
from docxindex.schema import DocumentIndex, DocumentNode

from .anchors import build_anchor_map
from .attachments import build_attachments
from .hierarchy import build_hierarchy_for_range, flatten_nodes
from .llm_expand import (
    EXPAND_BATCH_HARD_TOKENS,
    EXPAND_BATCH_OVERLAP_TOKENS,
    EXPAND_BATCH_TARGET_TOKENS,
    expand_large_leaves,
)
from .llm_summary import summarize_nodes
from .node_factory import make_node
from .splitter import split_long_leaves
from .tables import (
    TABLE_CHUNK_TARGET_TOKENS,
    TABLE_SPLIT_THRESHOLD_TOKENS,
    attach_table_nodes,
    collect_table_map,
)
from .token_budget import (
    PARAGRAPH_CHUNK_TARGET_TOKENS,
    PARAGRAPH_SPLIT_THRESHOLD_TOKENS,
    STRUCTURE_INLINE_BUDGET_TOKENS,
    STRUCTURE_PAGED_BUDGET_TOKENS,
)


def build_document_index(
    docx_path: Path,
    llm_expand: bool = False,
    llm_summary: bool = False,
    llm_settings: LLMSettings | None = None,
    cache_dir: Path | None = None,
    timer: Any | None = None,
    llm_concurrency: int = 10,
    paragraph_split_threshold_tokens: int = PARAGRAPH_SPLIT_THRESHOLD_TOKENS,
    paragraph_chunk_target_tokens: int = PARAGRAPH_CHUNK_TARGET_TOKENS,
    table_split_threshold_tokens: int = TABLE_SPLIT_THRESHOLD_TOKENS,
    table_chunk_target_tokens: int = TABLE_CHUNK_TARGET_TOKENS,
) -> DocumentIndex:
    with _stage(timer, "build.read_docx_items"):
        items = read_docx_items(docx_path)
    if not items:
        raise ValueError(f"No readable word/document.xml body found: {docx_path}")

    with _stage(timer, "build.detect_regions"):
        body_start = find_first_body_start(items)
        attachment_parent = find_attachment_parent(items, body_start)
        body_end = attachment_parent if attachment_parent is not None else len(items)
        use_cn_as_l1 = not any(item.kind == "p" and MAIN_SECTION_RE.match(item.text) for item in items[body_start:body_end])
        tail_start = find_tail_start(items, body_start, body_end)
        body_content_end = tail_start if tail_start is not None else body_end

    split_during_deterministic_build = not llm_expand
    roots: list[DocumentNode] = []

    with _stage(timer, "build.build_body_hierarchy"):
        frontmatter = make_node("frontmatter", "frontmatter", "合同首部", items, 0, max(body_start, 1), 0, None)
        body = make_node("body", "body", "正文", items, body_start, max(body_content_end, body_start + 1), 0, None)
        body.children = build_hierarchy_for_range(
            items,
            body_start,
            body_content_end,
            "body",
            "body",
            use_cn_as_l1,
            split_long_nodes=split_during_deterministic_build,
            paragraph_split_threshold_tokens=paragraph_split_threshold_tokens,
            paragraph_chunk_target_tokens=paragraph_chunk_target_tokens,
        )
        if body_start > 0:
            attach_table_nodes(
                frontmatter,
                items,
                0,
                body_start,
                split_threshold_tokens=table_split_threshold_tokens,
                chunk_target_tokens=table_chunk_target_tokens,
            )
        attach_table_nodes(
            body,
            items,
            body_start,
            body_content_end,
            split_threshold_tokens=table_split_threshold_tokens,
            chunk_target_tokens=table_chunk_target_tokens,
        )
        roots.extend([frontmatter, body])

    with _stage(timer, "build.build_tail"):
        if tail_start is not None and tail_start < body_end:
            tail = make_node("tail", "tail", "合同末尾", items, tail_start, body_end, 0, None)
            attach_table_nodes(
                tail,
                items,
                tail_start,
                body_end,
                split_threshold_tokens=table_split_threshold_tokens,
                chunk_target_tokens=table_chunk_target_tokens,
            )
            roots.append(tail)
        else:
            roots.append(DocumentNode(node_id="tail", node_type="tail", title="合同末尾", start_anchor="", end_anchor="", level=0))

    with _stage(timer, "build.build_attachments"):
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
            attachment_parent_node.children = build_attachments(
                items,
                attachment_parent + 1,
                len(items),
                attachment_parent_node.node_id,
                split_long_nodes=split_during_deterministic_build,
                paragraph_split_threshold_tokens=paragraph_split_threshold_tokens,
                paragraph_chunk_target_tokens=paragraph_chunk_target_tokens,
                table_split_threshold_tokens=table_split_threshold_tokens,
                table_chunk_target_tokens=table_chunk_target_tokens,
            )
            attachments.children.append(attachment_parent_node)
        roots.append(attachments)

    if llm_expand or llm_summary:
        with _stage(timer, "build.init_llm_client"):
            if llm_settings is None:
                llm_settings = LLMSettings.from_sources()
            client = LLMClient(llm_settings)
        if llm_expand:
            with _stage(timer, "build.llm_expand"):
                expand_large_leaves(
                    roots,
                    items,
                    client,
                    cache_dir,
                    concurrency=llm_concurrency,
                    split_threshold_tokens=paragraph_split_threshold_tokens,
                    chunk_target_tokens=paragraph_chunk_target_tokens,
                )
            with _stage(timer, "build.split_long_leaves_after_llm_expand"):
                split_long_leaves(
                    roots,
                    items,
                    paragraph_split_threshold_tokens,
                    paragraph_chunk_target_tokens,
                )
        if llm_summary:
            with _stage(timer, "build.llm_summary"):
                summarize_nodes(roots, client, cache_dir, concurrency=llm_concurrency)

    with _stage(timer, "build.finalize_index"):
        _fill_key_items(roots)
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
                "paragraph_split_threshold_tokens": paragraph_split_threshold_tokens,
                "paragraph_chunk_target_tokens": paragraph_chunk_target_tokens,
                "heading_mode": "agreement_fallback" if use_cn_as_l1 else "standard",
                "summary_tree_inline_budget_tokens": STRUCTURE_INLINE_BUDGET_TOKENS,
                "summary_tree_paged_budget_tokens": STRUCTURE_PAGED_BUDGET_TOKENS,
                "llm_expand_enabled": llm_expand,
                "llm_summary_enabled": llm_summary,
                "expand_batch_target_tokens": EXPAND_BATCH_TARGET_TOKENS,
                "expand_batch_hard_tokens": EXPAND_BATCH_HARD_TOKENS,
                "expand_batch_overlap_tokens": EXPAND_BATCH_OVERLAP_TOKENS,
                "llm_model": llm_settings.model if llm_settings else None,
                "llm_concurrency": llm_concurrency,
                "table_markdown_enabled": True,
                "table_split_threshold_tokens": table_split_threshold_tokens,
                "table_chunk_target_tokens": table_chunk_target_tokens,
            },
            nodes=[node.storage_view() for node in flat_nodes],
            root_nodes=[node.node_id for node in roots],
            structure_tree=[node.structure_view() for node in roots],
            anchor_map=build_anchor_map(items, flat_nodes),
            table_map=collect_table_map(items),
        )


def _fill_key_items(nodes: list[DocumentNode]) -> None:
    for node in nodes:
        if node.children:
            node.key_items = [child.title for child in node.children[:8] if child.title]
            _fill_key_items(node.children)


def _stage(timer: Any | None, name: str):
    if timer is None:
        return nullcontext()
    return timer.stage(name)
