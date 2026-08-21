from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree


class DocxPackage:
    def __init__(self, path: Path):
        self.path = path

    def read_xml(self, name: str) -> etree._Element:
        with zipfile.ZipFile(self.path) as docx:
            return etree.fromstring(docx.read(name))

    def try_read_xml(self, name: str) -> etree._Element | None:
        try:
            return self.read_xml(name)
        except KeyError:
            return None
