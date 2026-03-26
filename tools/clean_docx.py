"""
DOCX cleaner - Remove comments and reject tracked revisions.

Usage:
    from tools.clean_docx import DocxCleaner, clean_docx

    cleaner = DocxCleaner("合同.docx")
    clean_path = cleaner.clean()  # 返回临时文件路径
    # 使用完毕后删除: os.unlink(clean_path)
"""
import copy
import posixpath
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Union


class DocxCleaner:
    """清理 DOCX 文件中的修订和批注，返回临时文件路径"""

    WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    COMMENT_PART_RE = re.compile(r"^word/comments[^/]*\.xml$")
    PEOPLE_PART_RE = re.compile(r"^word/people\.xml$")
    WORD_PART_RE = re.compile(
        r"^word/(document|settings|footnotes|endnotes|header\d+|footer\d+)\.xml$"
    )

    DROP_MARKUP_TAGS = {
        "commentRangeStart", "commentRangeEnd", "commentReference",
        "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd",
        "customXmlInsRangeStart", "customXmlInsRangeEnd",
        "customXmlDelRangeStart", "customXmlDelRangeEnd",
        "customXmlMoveFromRangeStart", "customXmlMoveFromRangeEnd",
        "customXmlMoveToRangeStart", "customXmlMoveToRangeEnd",
    }

    DROP_PROPERTY_CHANGE_TAGS = {
        "numberingChange", "cellIns", "cellDel", "cellMerge",
    }

    DROP_SETTINGS_TAGS = {
        "trackRevisions", "doNotTrackMoves", "doNotTrackFormatting", "revisionView",
    }

    REJECT_DROP_TAGS = {"ins", "moveTo"}
    REJECT_UNWRAP_TAGS = {"del", "moveFrom"}

    PROPERTY_CHANGE_TAGS = {
        "pPrChange": "pPr", "rPrChange": "rPr", "tblPrChange": "tblPr",
        "tblPrExChange": "tblPrEx", "tblGridChange": "tblGrid",
        "tcPrChange": "tcPr", "trPrChange": "trPr", "sectPrChange": "sectPr",
    }

    RESTORE_TEXT_TAGS = {"delText": "t", "delInstrText": "instrText"}

    def __init__(self, input_path: Union[str, Path]):
        """
        初始化清理器

        Args:
            input_path: 输入的 DOCX 文件路径
        """
        self.input_path = Path(input_path)

    def clean(self) -> str:
        """
        执行清理

        Returns:
            清理后的临时文件路径（使用完毕后需手动删除）
        """
        if not self.input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {self.input_path}")

        # 创建临时文件
        tmp = tempfile.NamedTemporaryFile(delete=True, suffix=".docx")
        tmp.close()

        try:
            with zipfile.ZipFile(self.input_path) as source:
                names = source.namelist()
                removed_parts = self._get_comment_parts(names)
                removed_basenames = {posixpath.basename(n) for n in removed_parts}

                with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as target:
                    for item in source.infolist():
                        if item.filename in removed_parts:
                            continue

                        data = source.read(item.filename)

                        if self.WORD_PART_RE.match(item.filename):
                            data = self._clean_word_xml(
                                data,
                                is_settings=(item.filename == "word/settings.xml"),
                            )
                        elif item.filename == "[Content_Types].xml":
                            data = self._clean_content_types_xml(data, removed_parts)
                        elif item.filename.endswith(".rels"):
                            data = self._clean_relationships_xml(data, removed_basenames)

                        target.writestr(item, data)

        except zipfile.BadZipFile as exc:
            raise ValueError(f"无效的 DOCX 文件: {self.input_path}") from exc

        return tmp.name

    # ==================== 内部方法 ====================

    def _get_comment_parts(self, names):
        return [n for n in names if self.COMMENT_PART_RE.match(n) or self.PEOPLE_PART_RE.match(n)]

    def _local_name(self, tag: str) -> str:
        return tag.rsplit("}", 1)[1] if "}" in tag else tag

    def _unwrap_child(self, parent, index: int) -> int:
        child = parent[index]
        grandchildren = list(child)
        parent.remove(child)
        for offset, g in enumerate(grandchildren):
            parent.insert(offset + index, g)
        return len(grandchildren)

    def _restore_deleted_markup(self, element) -> None:
        tag_name = self._local_name(element.tag)
        if tag_name in self.RESTORE_TEXT_TAGS:
            element.tag = f"{{{self.WORD_NS}}}{self.RESTORE_TEXT_TAGS[tag_name]}"
        for child in list(element):
            self._restore_deleted_markup(child)

    def _revert_property_change(self, parent, index: int, tag_name: str) -> bool:
        change = parent[index]
        previous_tag = self.PROPERTY_CHANGE_TAGS[tag_name]
        previous = None

        for child in change:
            if self._local_name(child.tag) == previous_tag:
                previous = child
                break

        if previous is None:
            parent.remove(change)
            return True

        change_tail = change.tail
        parent.attrib.clear()
        parent.attrib.update(previous.attrib)
        parent.text = previous.text
        parent[:] = [copy.deepcopy(child) for child in previous]

        if change_tail:
            if len(parent):
                parent[-1].tail = (parent[-1].tail or "") + change_tail
            else:
                parent.text = (parent.text or "") + change_tail

        return True

    def _clean_word_element(self, element, *, is_settings: bool = False) -> None:
        from xml.etree import ElementTree as ET

        index = 0
        while index < len(element):
            child = element[index]
            self._clean_word_element(child, is_settings=is_settings)
            tag_name = self._local_name(child.tag)

            if tag_name in self.PROPERTY_CHANGE_TAGS:
                reverted = self._revert_property_change(element, index, tag_name)
                if reverted:
                    continue

            if tag_name in self.DROP_MARKUP_TAGS or tag_name in self.DROP_PROPERTY_CHANGE_TAGS:
                element.remove(child)
                continue

            if is_settings and tag_name in self.DROP_SETTINGS_TAGS:
                element.remove(child)
                continue

            if tag_name in self.REJECT_DROP_TAGS:
                element.remove(child)
                continue

            if tag_name in self.REJECT_UNWRAP_TAGS:
                self._restore_deleted_markup(child)
                inserted = self._unwrap_child(element, index)
                index += inserted
                continue

            index += 1

    def _clean_word_xml(self, data: bytes, *, is_settings: bool = False) -> bytes:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(data)
        self._clean_word_element(root, is_settings=is_settings)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _clean_content_types_xml(self, data: bytes, removed_parts: set) -> bytes:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(data)
        for child in list(root):
            if self._local_name(child.tag) != "Override":
                continue
            part_name = child.attrib.get("PartName", "").lstrip("/")
            if part_name in removed_parts:
                root.remove(child)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    def _clean_relationships_xml(self, data: bytes, removed_basenames: set) -> bytes:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(data)
        for child in list(root):
            if self._local_name(child.tag) != "Relationship":
                continue
            target = child.attrib.get("Target", "")
            basename = posixpath.basename(target)
            if basename in removed_basenames:
                root.remove(child)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)


# ==================== 便捷函数 ====================

def clean_docx(input_path: Union[str, Path]) -> str:
    """
    便捷函数：清理 DOCX 文件

    Args:
        input_path: 输入的 DOCX 文件路径

    Returns:
        清理后的临时文件路径（使用完毕后需手动删除）
    """
    return DocxCleaner(input_path).clean()
