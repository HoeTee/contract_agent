from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

from docx.oxml.ns import qn
from docx.table import Table
from lxml import etree


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
    row_start: int
    row_end: int
    column_start: int
    column_end: int
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
    rows: int
    columns: int
    header_rows: tuple[int, ...]
    row_markdown: tuple[str, ...]
    row_source_refs: tuple[tuple[str, ...], ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_path": self.table_path,
            "table_anchor_id": self.table_anchor_id,
            "markdown": self.markdown,
            "sources": {key: asdict(value) for key, value in self.sources.items()},
            "spans": [asdict(value) for value in self.spans],
            "cells": [asdict(value) for value in self.cells],
            "rows": self.rows,
            "columns": self.columns,
            "header_rows": list(self.header_rows),
            "row_markdown": list(self.row_markdown),
            "row_source_refs": [list(value) for value in self.row_source_refs],
            "warnings": list(self.warnings),
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


@dataclass
class _CanonicalCell:
    cell_id: str
    row_start: int
    row_end: int
    column_start: int
    column_end: int
    source_refs: tuple[str, ...]
    paragraphs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _GridSlot:
    cell: _CanonicalCell
    display_kind: str


def render_table_markdown(table: Table, table_path: str) -> TableMarkdownMapping:
    """Render a python-docx table while retaining exact XML provenance."""
    return render_table_element_markdown(table._tbl, table_path)


def render_table_element_markdown(
    table_element: etree._Element,
    table_path: str,
) -> TableMarkdownMapping:
    """Restore an OOXML table grid and render a source-addressable Markdown view."""
    table_id = f"path:{table_path}"
    sources: dict[str, MarkdownSource] = {}
    warnings: list[str] = []
    source_counter = 1
    cell_counter = 1
    active_vertical: dict[int, _CanonicalCell] = {}
    grid: list[list[_GridSlot | None]] = []

    grid_columns = len(table_element.findall(f"./{qn('w:tblGrid')}/{qn('w:gridCol')}"))
    rows = table_element.findall(f"./{qn('w:tr')}")
    header_rows = tuple(
        index
        for index, row in enumerate(rows, start=1)
        if row.find(f"./{qn('w:trPr')}/{qn('w:tblHeader')}") is not None
    )
    if not header_rows and rows:
        header_rows = (1,)

    for row_index, row_element in enumerate(rows, start=1):
        row_slots: list[_GridSlot | None] = [None] * grid_columns
        cursor = _row_grid_before(row_element)
        if cursor > len(row_slots):
            row_slots.extend([None] * (cursor - len(row_slots)))

        for physical_column, cell_element in enumerate(row_element.findall(f"./{qn('w:tc')}"), start=1):
            span = _cell_grid_span(cell_element)
            required = cursor + span
            if required > len(row_slots):
                row_slots.extend([None] * (required - len(row_slots)))

            merge_kind = _vertical_merge_kind(cell_element)
            if merge_kind == "continue":
                canonical = active_vertical.get(cursor)
                if canonical is None:
                    warnings.append(f"row {row_index} column {cursor + 1}: vMerge continuation has no restart")
                    canonical = _new_canonical_cell(
                        cell_element,
                        table_path,
                        table_id,
                        row_index,
                        cursor + 1,
                        physical_column,
                        span,
                        cell_counter,
                        source_counter,
                        sources,
                    )
                    cell_counter += 1
                    source_counter += len(canonical.source_refs)
                canonical.row_end = row_index
                display_kind = "vertical_inherited"
            else:
                canonical = _new_canonical_cell(
                    cell_element,
                    table_path,
                    table_id,
                    row_index,
                    cursor + 1,
                    physical_column,
                    span,
                    cell_counter,
                    source_counter,
                    sources,
                )
                cell_counter += 1
                source_counter += len(canonical.source_refs)
                display_kind = "original"

            for logical_column in range(cursor, cursor + span):
                slot_kind = display_kind
                if logical_column > cursor:
                    slot_kind = "horizontal_inherited" if merge_kind != "continue" else "merged_inherited"
                row_slots[logical_column] = _GridSlot(canonical, slot_kind)
                if merge_kind == "restart":
                    active_vertical[logical_column] = canonical
                elif merge_kind != "continue":
                    active_vertical.pop(logical_column, None)
            cursor += span

        grid.append(row_slots)
        grid_columns = max(grid_columns, len(row_slots))

    for row_slots in grid:
        if len(row_slots) < grid_columns:
            row_slots.extend([None] * (grid_columns - len(row_slots)))

    return _render_grid(
        table_path=table_path,
        table_id=table_id,
        grid=grid,
        grid_columns=grid_columns,
        header_rows=header_rows,
        sources=sources,
        warnings=warnings,
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


def _new_canonical_cell(
    cell_element: etree._Element,
    table_path: str,
    table_id: str,
    row_index: int,
    logical_column: int,
    physical_column: int,
    span: int,
    cell_counter: int,
    source_counter: int,
    sources: dict[str, MarkdownSource],
) -> _CanonicalCell:
    refs: list[str] = []
    paragraphs: list[tuple[str, str]] = []
    block_index = 0
    paragraph_index = 0
    for child in cell_element:
        local_name = etree.QName(child).localname
        if local_name not in {"p", "tbl", "sdt"}:
            continue
        block_index += 1
        paragraph_elements = [child] if local_name == "p" else child.findall(f".//{qn('w:p')}")
        for paragraph_element in paragraph_elements:
            if _has_ancestor_within(paragraph_element, child, {"del", "moveFrom"}):
                continue
            original_text = _paragraph_visible_text(paragraph_element).strip()
            if not original_text:
                continue
            paragraph_index += 1
            source_ref = f"S{source_counter + len(refs):04d}"
            paragraph_path = f"{table_path}/r{row_index}c{physical_column}/p{block_index}"
            if paragraph_index > 1 and block_index == 1:
                paragraph_path = f"{paragraph_path}_{paragraph_index}"
            sources[source_ref] = MarkdownSource(
                source_ref=source_ref,
                table_anchor_id=table_id,
                paragraph_anchor_id=f"path:{paragraph_path}",
                row=row_index,
                column=logical_column,
                paragraph=paragraph_index,
                original_text=original_text,
                xml_path=paragraph_path,
            )
            refs.append(source_ref)
            paragraphs.append((source_ref, original_text))
    return _CanonicalCell(
        cell_id=f"C{cell_counter:04d}",
        row_start=row_index,
        row_end=row_index,
        column_start=logical_column,
        column_end=logical_column + span - 1,
        source_refs=tuple(refs),
        paragraphs=tuple(paragraphs),
    )


def _render_grid(
    table_path: str,
    table_id: str,
    grid: list[list[_GridSlot | None]],
    grid_columns: int,
    header_rows: tuple[int, ...],
    sources: dict[str, MarkdownSource],
    warnings: list[str],
) -> TableMarkdownMapping:
    output: list[str] = []
    spans: list[MarkdownSpan] = []
    cells: list[CellMapping] = []
    row_markdown: list[str] = []
    row_source_refs: list[tuple[str, ...]] = []
    length = 0

    def append(text: str) -> tuple[int, int]:
        nonlocal length
        start = length
        output.append(text)
        length += len(text)
        return start, length

    append(f"<!-- table_id: {table_id} -->\n")
    for row_index, row_slots in enumerate(grid, start=1):
        row_start = length
        refs_in_row: list[str] = []
        append("| ")
        for column_index in range(1, grid_columns + 1):
            slot = row_slots[column_index - 1] if column_index - 1 < len(row_slots) else None
            cell_start = length
            if slot is None:
                append("")
                canonical = _CanonicalCell("", row_index, row_index, column_index, column_index, (), ())
                display_kind = "empty"
            else:
                canonical = slot.cell
                refs_in_row.extend(canonical.source_refs)
                display_kind = slot.display_kind
                if display_kind == "original":
                    for paragraph_index, (source_ref, original_text) in enumerate(canonical.paragraphs):
                        if paragraph_index:
                            append("<br>")
                        text_start, text_end = append(_escape_markdown(original_text))
                        spans.append(MarkdownSpan(text_start, text_end, source_ref))
                        append(f" [{source_ref}]")
                else:
                    source_ref = canonical.source_refs[0] if canonical.source_refs else canonical.cell_id
                    direction = "同左" if display_kind == "horizontal_inherited" else "同上"
                    marker = f"↳{direction}{source_ref}" if source_ref else ""
                    text_start, text_end = append(marker)
                    if canonical.source_refs:
                        spans.append(MarkdownSpan(text_start, text_end, canonical.source_refs[0], synthetic=True))
            cell_end = length
            cells.append(
                CellMapping(
                    row=row_index,
                    column=column_index,
                    canonical_row=canonical.row_start,
                    canonical_column=canonical.column_start,
                    row_start=canonical.row_start,
                    row_end=canonical.row_end,
                    column_start=canonical.column_start,
                    column_end=canonical.column_end,
                    source_refs=canonical.source_refs,
                    display_kind=display_kind,
                    md_start=cell_start,
                    md_end=cell_end,
                )
            )
            append(" | ")
        append("\n")
        row_end = length
        row_markdown.append("".join(output)[row_start:row_end])
        row_source_refs.append(tuple(dict.fromkeys(refs_in_row)))
        if row_index == 1:
            append("| " + " | ".join("---" for _ in range(grid_columns)) + " |\n")

    return TableMarkdownMapping(
        table_path=table_path,
        table_anchor_id=table_id,
        markdown="".join(output),
        sources=sources,
        spans=tuple(spans),
        cells=tuple(cells),
        rows=len(grid),
        columns=grid_columns,
        header_rows=header_rows,
        row_markdown=tuple(row_markdown),
        row_source_refs=tuple(row_source_refs),
        warnings=tuple(warnings),
    )


def _row_grid_before(row_element: etree._Element) -> int:
    node = row_element.find(f"./{qn('w:trPr')}/{qn('w:gridBefore')}")
    return _int_attr(node, qn("w:val"), 0)


def _cell_grid_span(cell_element: etree._Element) -> int:
    node = cell_element.find(f"./{qn('w:tcPr')}/{qn('w:gridSpan')}")
    return max(1, _int_attr(node, qn("w:val"), 1))


def _vertical_merge_kind(cell_element: etree._Element) -> str | None:
    node = cell_element.find(f"./{qn('w:tcPr')}/{qn('w:vMerge')}")
    if node is None:
        return None
    return "restart" if node.get(qn("w:val")) == "restart" else "continue"


def _int_attr(node: etree._Element | None, name: str, default: int) -> int:
    if node is None:
        return default
    try:
        return int(node.get(name, str(default)))
    except ValueError:
        return default


def _paragraph_visible_text(paragraph_element: etree._Element) -> str:
    chars: list[str] = []
    for element in paragraph_element.iter():
        if etree.QName(element).localname != "t":
            continue
        if _has_ancestor_within(element, paragraph_element, {"del", "moveFrom"}):
            continue
        chars.append(element.text or "")
    return "".join(chars)


def _has_ancestor_within(element: etree._Element, stop: etree._Element, names: set[str]) -> bool:
    parent = element.getparent()
    while parent is not None and parent is not stop:
        if etree.QName(parent).localname in names:
            return True
        parent = parent.getparent()
    return False


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
