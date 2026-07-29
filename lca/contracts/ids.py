"""契约层纯工具：稳定 id / 时间戳生成。

提供全局唯一的 trace-id / span-id 生成和 UTC 时间戳。
被 contracts 各模块及上层广泛引用，不得引入业务依赖。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

# uuid4 hex 截取长度：12 位 hex = 48 bit 随机性，碰撞概率极低且 id 简短
_ID_SUFFIX_LEN: int = 12


def utc_now() -> datetime:
    """返回当前 UTC 时间（带 timezone）。"""
    return datetime.now(timezone.utc)


def new_id(prefix: str) -> str:
    """生成 ``{prefix}_{hex12}`` 格式的唯一 id。"""
    return f"{prefix}_{uuid.uuid4().hex[:_ID_SUFFIX_LEN]}"
