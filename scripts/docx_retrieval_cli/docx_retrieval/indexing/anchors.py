from __future__ import annotations

from docx_retrieval.schema import AnchorRecord, BodyItem, DocumentNode


def build_anchor_map(items: list[BodyItem], flat_nodes: list[DocumentNode]) -> dict[str, AnchorRecord]:
    anchor_order = {item.anchor: item.body_child_index for item in items}
    by_anchor: dict[str, AnchorRecord] = {}
    for item in items:
        item_order = item.body_child_index
        owner = None
        for node in reversed(flat_nodes):
            start_order = anchor_order.get(node.start_anchor)
            end_order = anchor_order.get(node.end_anchor)
            if start_order is not None and end_order is not None and start_order <= item_order <= end_order:
                owner = node.node_id
                break
        by_anchor[item.anchor] = AnchorRecord(
            body_child_index=item.body_child_index,
            type=item.kind,
            text=item.text,
            node_id=owner,
            page_start=item.page_start,
            page_end=item.page_end,
            xml_path=item.xml_path,
        )
    return by_anchor
