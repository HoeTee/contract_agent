from __future__ import annotations

import json
from typing import Any

from fastapi import Response


def pretty_json_response(data: Any, *, status_code: int = 200) -> Response:
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        status_code=status_code,
        media_type="application/json",
    )
