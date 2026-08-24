from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request

from config import API_META_FIELDS, API_META_REQUIRED


class MetaFieldsValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def header_name_for_meta_field(field_name: str) -> str:
    kebab = re.sub(r"(?<!^)(?=[A-Z])", "-", field_name).replace("_", "-").lower()
    return f"x-{kebab}"


def extract_configured_meta_fields(data: Mapping[str, Any]) -> dict[str, str]:
    meta_fields: dict[str, str] = {}
    missing: list[str] = []
    invalid: list[str] = []

    for field_name in API_META_FIELDS:
        raw_value = data.get(field_name)
        if raw_value is None:
            value = ""
        elif isinstance(raw_value, str):
            value = raw_value.strip()
        else:
            value = ""
            invalid.append(field_name)
        meta_fields[field_name] = value
        if API_META_REQUIRED and not value:
            missing.append(field_name)

    if invalid:
        raise MetaFieldsValidationError(
            "META_FIELDS_INVALID",
            f"元数据字段必须是字符串：{', '.join(invalid)}",
        )
    if missing:
        raise MetaFieldsValidationError(
            "META_FIELDS_REQUIRED",
            f"缺少必填字符串字段：{', '.join(missing)}",
        )

    return meta_fields


async def extract_api_meta_fields(request: Request) -> dict[str, str]:
    form = await request.form()
    try:
        return extract_configured_meta_fields(form)
    except MetaFieldsValidationError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc


def build_meta_response_headers(meta_fields: dict[str, str]) -> dict[str, str]:
    return {
        header_name_for_meta_field(field_name): field_value
        for field_name, field_value in meta_fields.items()
    }
