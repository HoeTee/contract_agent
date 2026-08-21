from __future__ import annotations

from lxml import etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
}
W_NS = NS["w"]


def w_tag(local_name: str) -> str:
    return f"{{{W_NS}}}{local_name}"


def attr_value(element: etree._Element | None, name: str = "val") -> str | None:
    if element is None:
        return None
    return element.get(w_tag(name))


def xpath_one(element: etree._Element, query: str) -> etree._Element | None:
    result = element.xpath(query, namespaces=NS)
    return result[0] if result else None


def text_of(element: etree._Element) -> str:
    parts = element.xpath(".//w:t/text() | .//w:delText/text()", namespaces=NS)
    return "".join(str(part) for part in parts).strip()


def xml_path(element: etree._Element) -> str:
    tree = element.getroottree()
    return tree.getpath(element)
