"""案件JSONの出力（要件IDつきの受け渡し用）。"""
from __future__ import annotations

import json


def dumps(p: dict) -> bytes:
    return json.dumps(p, ensure_ascii=False, indent=1, default=str).encode("utf-8")
