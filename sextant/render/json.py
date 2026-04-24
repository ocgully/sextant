"""JSON renderer — deterministic, stable key order."""
from __future__ import annotations

import json


def render_json(result) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False, default=str)
