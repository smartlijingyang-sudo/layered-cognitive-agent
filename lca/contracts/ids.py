"""契约层纯工具：稳定 id / 时间戳生成。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
