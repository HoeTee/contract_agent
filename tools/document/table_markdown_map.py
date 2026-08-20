from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

from docx.table import Table
from docx.text.paragraph import Paragraph

from tools.document.docx_anchor_index import (
    iter_blocks,
    paragraph_anchor_id,
    paragraph_visible_text,
    table_anchor_id,
)


@dataclass(frozen=True)
class MarkdownSource:
    source_ref: str
    table_anchor_id: str
    paragraph_anchor_id: str
    row: int
    column: int
    paragraph: int
    original_text: str
    xml_path: str


@dataclass(frozen=True)
class MarkdownSpan:
    md_start: int
    md_end: int
    source_ref: str
    synthetic: bool = False


@dataclass(frozen=True)
class CellMapping:
    row: int
    column: int
    canonical_row: int
    canonical_column: int
    source_refs: tuple[str, ...]
    display_kind: str
    md_start: int
    md_end: int


@dataclass(frozen=True)
class TableMarkdownMapping:
    table_path: str
    table_anchor_id: str
    markdown: str
    sources: dict[str, MarkdownSource]
    spans: tuple[MarkdownSpan, ...]
    cells: tuple[CellMapping, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_path": self.table_path,
            "table_anchor_id": self.table_anchor_id,
            "markdown": self.markdown,
            "sources": {key: asdict(value) for key, value in self.sources.items()},
            "spans": [asdict(value) for value in self.spans],
            "cells": [asdict(value) for value in self.cells],
        }


@dataclass(frozen=True)
class SourceResolution:
    status: str
    source_ref: str | None = None
    paragraph_anchor_id: str | None = None
    table_anchor_id: str | None = None
    matched_original_text: str | None = None
    md_start: int | None = None
    md_end: int | None = None
    candidates: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def render_table_markdown(table: Table, table_path: str) -> TableMarkdownMapping:
    """Render a DOCX table as Markdown while retaining exact paragraph provenance."""
    table_id = table_anchor_id(table, table_path)
    sources: dict[str, MarkdownSource] = {}
    cell_data: dict[Any, dict[str, Any]] = {}
    counter = 1

    for row_index, row in enumerate(table.rows, start=1):
        for column_index, cell in enumerate(row.cells, start=1):
            tc = cell._tc
            if tc in cell_data:
                continue
            refs: list[str] = []
            paragraphs: list[tuple[str, str]] = []
            cell_path = f"{table_path}/r{row_index}c{column_index}"
            for block_index, block in enumerate(iter_blocks(cell), start=1):
                if not isinstance(block, Paragraph):
                    continue
                original_text = paragraph_visible_text(block).strip()
                if not original_text:
                    continue
                source_ref = f"S{counter:04d}"
                counter += 1
                paragraph_path = f"{cell_path}/p{block_index}"
                sources[source_ref] = MarkdownSource(
                    source_ref=source_ref,
                    table_anchor_id=table_id,
                    paragraph_anchor_id=paragraph_anchor_id(block, paragraph_path),
                    row=row_index,
                    column=column_index,
                    paragraph=block_index,
                    original_text=original_text,
                    xml_path=paragraph_path,
                )
                refs.append(source_ref)
                paragraphs.append((source_ref, original_text))
            cell_data[tc] = {
                "row": row_index,
                "column": column_index,
                "refs": tuple(refs),
                "paragraphs": tuple(paragraphs),
            }

    output: list[str] = []
    spans: list[MarkdownSpan] = []
    cells: list[CellMapping] = []
    length = 0

    def append(text: str) -> tuple[int, int]:
        nonlocal length
        start = length
        output.append(text)
        length += len(text)
        return start, length

    append(f"<!-- table_anchor_id: {table_id} -->\n")
    for row_index, row in enumerate(table.rows, start=1):
        append("| ")
        seen_in_row: set[Any] = set()
        for column_index, cell in enumerate(row.cells, start=1):
            data = cell_data[cell._tc]
            cell_start = length
            canonical = data["row"] == row_index and data["column"] == column_index
            if canonical:
                for paragraph_index, (source_ref, original_text) in enumerate(data["paragraphs"]):
                    if paragraph_index:
                        append("<br>")
                    escaped = _escape_markdown(original_text)
                    text_start, text_end = append(escaped)
                    spans.append(MarkdownSpan(text_start, text_end, source_ref))
                    append(f" [{source_ref}]")
                display_kind = "original"
            else:
                direction = "同左" if cell._tc in seen_in_row else "同上"
                source_ref = data["refs"][0] if data["refs"] else ""
                marker = f"{direction} [{source_ref}]" if source_ref else direction
                text_start, text_end = append(marker)
                if source_ref:
                    spans.append(MarkdownSpan(text_start, text_end, source_ref, synthetic=True))
                display_kind = "inherited"
            cell_end = length
            cells.append(
                CellMapping(
                    row=row_index,
                    column=column_index,
                    canonical_row=data["row"],
                    canonical_column=data["column"],
                    source_refs=data["refs"],
                    display_kind=display_kind,
                    md_start=cell_start,
                    md_end=cell_end,
                )
            )
            seen_in_row.add(cell._tc)
            append(" | ")
        append("\n")
        if row_index == 1:
            append("| " + " | ".join("---" for _ in row.cells) + " |\n")

    return TableMarkdownMapping(
        table_path=table_path,
        table_anchor_id=table_id,
        markdown="".join(output),
        sources=sources,
        spans=tuple(spans),
        cells=tuple(cells),
    )


def resolve_agent_evidence(
    mapping: TableMarkdownMapping,
    quoted_text: str,
    source_ref: str | None = None,
) -> SourceResolution:
    """Resolve agent evidence to one original DOCX paragraph without guessing."""
    quoted = (quoted_text or "").strip()
    if source_ref:
        source = mapping.sources.get(source_ref)
        if source is None:
            return SourceResolution(status="not_found", source_ref=source_ref)
        matched = _match_original_text(source.original_text, quoted)
        if matched is None:
            return SourceResolution(status="source_mismatch", source_ref=source_ref)
        span = next((item for item in mapping.spans if item.source_ref == source_ref and not item.synthetic), None)
        return _resolved(source, matched, span)

    occurrences = _markdown_occurrences(mapping.markdown, quoted)
    candidates: dict[str, tuple[MarkdownSource, MarkdownSpan]] = {}
    for start, end in occurrences:
        for span in mapping.spans:
            if span.synthetic:
                continue
            if span.md_start <= start and end <= span.md_end:
                source = mapping.sources[span.source_ref]
                matched = _match_original_text(source.original_text, quoted)
                if matched is not None:
                    candidates[span.source_ref] = (source, span)
    if not candidates:
        return SourceResolution(status="not_found")
    if len(candidates) > 1:
        return SourceResolution(status="ambiguous", candidates=tuple(sorted(candidates)))
    source, span = next(iter(candidates.values()))
    return _resolved(source, _match_original_text(source.original_text, quoted) or quoted, span)


def cell_source_refs(mapping: TableMarkdownMapping, row: int, column: int) -> tuple[str, ...]:
    for cell in mapping.cells:
        if cell.row == row and cell.column == column:
            return cell.source_refs
    return ()


def _resolved(source: MarkdownSource, matched: str, span: MarkdownSpan | None) -> SourceResolution:
    return SourceResolution(
        status="matched",
        source_ref=source.source_ref,
        paragraph_anchor_id=source.paragraph_anchor_id,
        table_anchor_id=source.table_anchor_id,
        matched_original_text=matched,
        md_start=span.md_start if span else None,
        md_end=span.md_end if span else None,
    )


def _escape_markdown(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _normalized(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def _match_original_text(original: str, quoted: str) -> str | None:
    if not quoted:
        return None
    if quoted in original:
        return quoted
    normalized_quote = _normalized(quoted)
    if normalized_quote and normalized_quote == _normalized(original):
        return original
    return None


def _markdown_occurrences(markdown: str, quoted: str) -> list[tuple[int, int]]:
    if not quoted:
        return []
    exact = [(match.start(), match.end()) for match in re.finditer(re.escape(quoted), markdown)]
    if exact:
        return exact
    normalized_quote = _normalized(quoted)
    if not normalized_quote:
        return []
    normalized_chars: list[str] = []
    offsets: list[int] = []
    for index, char in enumerate(markdown):
        normalized = unicodedata.normalize("NFKC", char)
        for item in normalized:
            if item.isspace():
                continue
            normalized_chars.append(item)
            offsets.append(index)
    normalized_markdown = "".join(normalized_chars)
    result = []
    start = 0
    while True:
        found = normalized_markdown.find(normalized_quote, start)
        if found < 0:
            break
        result.append((offsets[found], offsets[found + len(normalized_quote) - 1] + 1))
        start = found + 1
    return result
