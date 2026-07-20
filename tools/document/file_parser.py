from __future__ import annotations

from tools.document.parsers.default_file_parser import DefaultFileParser


class FileParser:
    """Facade over the supported file parsing strategies."""

    @staticmethod
    def parse_file(file_path: str) -> str:
        """Parse a DOCX file with the default local parser."""
        return DefaultFileParser.parse_file(file_path)

