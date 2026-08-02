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


def remaining_seconds(deadline: datetime, *, now: datetime | None = None) -> float:
    """deadline 距今剩余的 wall-clock 秒数(可能为负,代表已过期)。

    deadline 与 now 必须是同一 epoch 的 timezone-aware datetime(wall-clock/UTC)。
    禁止把 ``asyncio.get_running_loop().time()`` 之类的 monotonic float 传入 ——
    这正是问题 B 的根因。本函数的类型签名(要求 ``datetime``)已经在类型检查层面
    拒绝 monotonic float 混入:不存在"不小心传错"的写法。
    """
    return (deadline - (now or utc_now())).total_seconds()


def elapsed_seconds(started_at: datetime, *, now: datetime | None = None) -> float:
    """自 started_at 起经过的 wall-clock 秒数。"""
    return ((now or utc_now()) - started_at).total_seconds()
