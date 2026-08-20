from __future__ import annotations

import copy
import secrets
from datetime import datetime, timezone

from docx import Document
from docx.oxml.ns import qn
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from lxml import etree

from tools.document.reporting.docx_report import (
    DocxReportGenerator,
    TextAnchor,
)


COMMENTS_RELTYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
)
COMMENTS_EXTENDED_RELTYPE = (
    "http://schemas.microsoft.com/office/2011/relationships/commentsExtended"
)
COMMENTS_IDS_RELTYPE = (
    "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds"
)
COMMENTS_EXTENSIBLE_RELTYPE = (
    "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible"
)
PEOPLE_RELTYPE = "http://schemas.microsoft.com/office/2011/relationships/people"

W_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W14_NAMESPACE = "http://schemas.microsoft.com/office/word/2010/wordml"
W15_NAMESPACE = "http://schemas.microsoft.com/office/word/2012/wordml"
W16CID_NAMESPACE = "http://schemas.microsoft.com/office/word/2016/wordml/cid"
W16CEX_NAMESPACE = "http://schemas.microsoft.com/office/word/2018/wordml/cex"


def add_modern_comments_to_doc(doc: Document, comments_data: list[dict]) -> Document:
    """Write comments with the five linked parts emitted by current Word versions."""
    comments_part = _get_or_create_part(
        doc,
        COMMENTS_RELTYPE,
        "/word/comments.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
        etree.Element(f"{{{W_NAMESPACE}}}comments", nsmap={"w": W_NAMESPACE, "w14": W14_NAMESPACE}),
    )
    extended_part = _get_or_create_part(
        doc,
        COMMENTS_EXTENDED_RELTYPE,
        "/word/commentsExtended.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml",
        etree.Element(f"{{{W15_NAMESPACE}}}commentsEx", nsmap={"w15": W15_NAMESPACE}),
    )
    ids_part = _get_or_create_part(
        doc,
        COMMENTS_IDS_RELTYPE,
        "/word/commentsIds.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsIds+xml",
        etree.Element(
            f"{{{W16CID_NAMESPACE}}}commentsIds",
            nsmap={"w16cid": W16CID_NAMESPACE},
        ),
    )
    extensible_part = _get_or_create_part(
        doc,
        COMMENTS_EXTENSIBLE_RELTYPE,
        "/word/commentsExtensible.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtensible+xml",
        etree.Element(
            f"{{{W16CEX_NAMESPACE}}}commentsExtensible",
            nsmap={"w16cex": W16CEX_NAMESPACE},
        ),
    )
    people_part = _get_or_create_part(
        doc,
        PEOPLE_RELTYPE,
        "/word/people.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.people+xml",
        etree.Element(f"{{{W15_NAMESPACE}}}people", nsmap={"w15": W15_NAMESPACE}),
    )

    comments = etree.fromstring(comments_part.blob)
    extended = etree.fromstring(extended_part.blob)
    comment_ids = etree.fromstring(ids_part.blob)
    extensible = etree.fromstring(extensible_part.blob)
    people = etree.fromstring(people_part.blob)

    used_para_ids = _attribute_values(
        [comments, extended, comment_ids],
        [
            f"{{{W14_NAMESPACE}}}paraId",
            f"{{{W15_NAMESPACE}}}paraId",
            f"{{{W16CID_NAMESPACE}}}paraId",
        ],
    )
    used_durable_ids = _attribute_values(
        [comment_ids, extensible],
        [f"{{{W16CID_NAMESPACE}}}durableId", f"{{{W16CEX_NAMESPACE}}}durableId"],
    )
    existing_ids = []
    for comment in comments.findall(f"{{{W_NAMESPACE}}}comment"):
        try:
            existing_ids.append(int(comment.get(qn("w:id"))))
        except (TypeError, ValueError):
            pass
    next_comment_id = max(existing_ids, default=-1) + 1

    _backfill_comment_ids(comments, comment_ids, used_para_ids, used_durable_ids)
    existing_authors = {
        person.get(f"{{{W15_NAMESPACE}}}author", "")
        for person in people.findall(f"{{{W15_NAMESPACE}}}person")
    }
    paragraph_template, reference_template = _comment_templates(comments)

    for item in comments_data:
        anchor = item.get("anchor")
        text = str(item.get("comment_text") or "")
        author = str(item.get("author") or "TableMappingTest")
        if anchor is None or not text:
            continue

        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        comment = etree.SubElement(comments, qn("w:comment"))
        comment.set(qn("w:id"), str(next_comment_id))
        comment.set(qn("w:author"), author)
        comment.set(qn("w:date"), now_utc.isoformat().replace("+00:00", "Z"))
        comment.set(qn("w:initials"), "")

        last_para_id = ""
        for line_number, line in enumerate(text.split("\n") or [""], start=1):
            last_para_id = _new_hex_id(used_para_ids)
            paragraph = etree.SubElement(comment, qn("w:p"))
            paragraph.set(f"{{{W14_NAMESPACE}}}paraId", last_para_id)
            paragraph.set(f"{{{W14_NAMESPACE}}}textId", "77777777")
            if paragraph_template is not None:
                paragraph.append(copy.deepcopy(paragraph_template))
            if line_number == 1:
                paragraph.append(
                    copy.deepcopy(reference_template)
                    if reference_template is not None
                    else _new_annotation_reference_run()
                )
            if line:
                run = etree.SubElement(paragraph, qn("w:r"))
                text_element = etree.SubElement(run, qn("w:t"))
                text_element.set(qn("xml:space"), "preserve")
                text_element.text = line

        comment_ex = etree.SubElement(extended, f"{{{W15_NAMESPACE}}}commentEx")
        comment_ex.set(f"{{{W15_NAMESPACE}}}paraId", last_para_id)
        comment_ex.set(f"{{{W15_NAMESPACE}}}done", "0")

        durable_id = _new_hex_id(used_durable_ids)
        id_item = etree.SubElement(comment_ids, f"{{{W16CID_NAMESPACE}}}commentId")
        id_item.set(f"{{{W16CID_NAMESPACE}}}paraId", last_para_id)
        id_item.set(f"{{{W16CID_NAMESPACE}}}durableId", durable_id)

        extensible_item = etree.SubElement(
            extensible, f"{{{W16CEX_NAMESPACE}}}commentExtensible"
        )
        extensible_item.set(f"{{{W16CEX_NAMESPACE}}}durableId", durable_id)
        extensible_item.set(
            f"{{{W16CEX_NAMESPACE}}}dateUtc",
            now_utc.isoformat().replace("+00:00", "Z"),
        )

        if author not in existing_authors:
            person = etree.SubElement(people, f"{{{W15_NAMESPACE}}}person")
            person.set(f"{{{W15_NAMESPACE}}}author", author)
            presence = etree.SubElement(person, f"{{{W15_NAMESPACE}}}presenceInfo")
            presence.set(f"{{{W15_NAMESPACE}}}providerId", "None")
            presence.set(f"{{{W15_NAMESPACE}}}userId", author)
            existing_authors.add(author)

        if isinstance(anchor, TextAnchor):
            DocxReportGenerator._add_comment_markers_to_text_range(anchor, next_comment_id)
        else:
            DocxReportGenerator._add_comment_markers_to_paragraph(anchor, next_comment_id)
        next_comment_id += 1

    for part, element in [
        (comments_part, comments),
        (extended_part, extended),
        (ids_part, comment_ids),
        (extensible_part, extensible),
        (people_part, people),
    ]:
        _update_part(part, element)
    return doc


def _backfill_comment_ids(comments, comment_ids, used_para_ids, used_durable_ids) -> None:
    mapped_para_ids = {
        item.get(f"{{{W16CID_NAMESPACE}}}paraId", "").upper()
        for item in comment_ids.findall(f"{{{W16CID_NAMESPACE}}}commentId")
    }
    for comment in comments.findall(f"{{{W_NAMESPACE}}}comment"):
        paragraphs = comment.findall(f"{{{W_NAMESPACE}}}p")
        if not paragraphs:
            continue
        para_id = paragraphs[-1].get(f"{{{W14_NAMESPACE}}}paraId", "").upper()
        if not para_id:
            para_id = _new_hex_id(used_para_ids)
            paragraphs[-1].set(f"{{{W14_NAMESPACE}}}paraId", para_id)
            paragraphs[-1].set(f"{{{W14_NAMESPACE}}}textId", "77777777")
        if para_id in mapped_para_ids:
            continue
        durable_id = para_id if para_id not in used_durable_ids else _new_hex_id(used_durable_ids)
        used_durable_ids.add(durable_id)
        item = etree.SubElement(comment_ids, f"{{{W16CID_NAMESPACE}}}commentId")
        item.set(f"{{{W16CID_NAMESPACE}}}paraId", para_id)
        item.set(f"{{{W16CID_NAMESPACE}}}durableId", durable_id)
        mapped_para_ids.add(para_id)


def _comment_templates(comments):
    first_paragraph = comments.find(f".//{{{W_NAMESPACE}}}p")
    paragraph_properties = None
    reference_run = None
    if first_paragraph is not None:
        ppr = first_paragraph.find(qn("w:pPr"))
        if ppr is not None:
            paragraph_properties = ppr
        for run in first_paragraph.findall(qn("w:r")):
            if run.find(qn("w:annotationRef")) is not None:
                reference_run = run
                break
    return paragraph_properties, reference_run


def _new_annotation_reference_run():
    run = etree.Element(qn("w:r"))
    run_properties = etree.SubElement(run, qn("w:rPr"))
    style = etree.SubElement(run_properties, qn("w:rStyle"))
    style.set(qn("w:val"), "CommentReference")
    etree.SubElement(run, qn("w:annotationRef"))
    return run


def _attribute_values(elements, attribute_names) -> set[str]:
    result: set[str] = set()
    for element in elements:
        for attribute_name in attribute_names:
            result.update(
                value.upper()
                for value in element.xpath(f"//@*[local-name()='{attribute_name.split('}')[-1]}']")
                if value
            )
    return result


def _new_hex_id(used_ids: set[str]) -> str:
    while True:
        value = secrets.token_hex(4).upper()
        if value not in used_ids:
            used_ids.add(value)
            return value


def _get_or_create_part(doc, reltype, partname, content_type, root):
    for relationship in doc.part.rels.values():
        if relationship.reltype == reltype:
            return relationship.target_part
    part = Part(
        partname=PackURI(partname),
        content_type=content_type,
        blob=etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True),
        package=doc.part.package,
    )
    doc.part.relate_to(part, reltype)
    return part


def _update_part(part, element) -> None:
    part._blob = etree.tostring(
        element,
        xml_declaration=True,
        encoding="UTF-8",
        standalone=True,
    )
    if hasattr(part, "_element"):
        part._element = element
