from __future__ import annotations

import re

from fastapi import HTTPException, Request

from config import API_META_FIELDS, API_META_REQUIRED


def header_name_for_meta_field(field_name: str) -> str:
    kebab = re.sub(r"(?<!^)(?=[A-Z])", "-", field_name).replace("_", "-").lower()
    return f"x-{kebab}"


async def extract_api_meta_fields(request: Request) -> dict[str, str]:
    form = await request.form()
    meta_fields: dict[str, str] = {}
    missing: list[str] = []

    for field_name in API_META_FIELDS:
        raw_value = form.get(field_name)
        value = raw_value.strip() if isinstance(raw_value, str) else ""
        meta_fields[field_name] = value
        if API_META_REQUIRED and not value:
            missing.append(field_name)

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"缺少必填字符串字段：{', '.join(missing)}",
        )

    return meta_fields


def build_meta_response_headers(meta_fields: dict[str, str]) -> dict[str, str]:
    return {
        header_name_for_meta_field(field_name): field_value
        for field_name, field_value in meta_fields.items()
    }
