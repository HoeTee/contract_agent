from __future__ import annotations

from typing import Any

from tools.document.parsers.default_file_parser import DefaultFileParser
from tools.document.parsers.mineru_file_parser import (
    parse_file_to_content_bundle as parse_file_to_content_bundle_via_mineru,
    parse_file_with_mineru,
)


class FileParser:
    """Facade over the supported file parsing strategies."""

    @staticmethod
    def parse_file(file_path: str) -> str:
        """Parse a DOCX file with the default local parser."""
        return DefaultFileParser.parse_file(file_path)

    @staticmethod
    async def parse_file_with_mineru(file_path: str) -> str:
        """Parse a file through the MinerU-first strategy chain."""
        return await parse_file_with_mineru(file_path)

    @staticmethod
    async def parse_file_to_content_bundle_via_mineru(
        file_path: str,
        include_middle_json: bool = False,
    ) -> dict[str, Any]:
        """Return the structured MinerU-first parsing bundle."""
        return await parse_file_to_content_bundle_via_mineru(
            file_path,
            include_middle_json=include_middle_json,
        )

