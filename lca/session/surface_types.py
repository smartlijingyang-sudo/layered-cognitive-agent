"""DSH-aligned session surface event taxonomy.

``surface/*`` session event 类型的 single source: 由 RunSessionWriter 生产
（ADR-0268 §6），被 session catalog（``known_session_event_types``）识别。
新增 DSH surface 类型时只改这里 —— 生产者与读路径闭集自动跟随，
无需人肉同步 catalog。
"""

from __future__ import annotations

DEVELOPER_MESSAGE_TYPE: str = "surface/developer_message"
"""Cron handoff 作为 developer 消息注入父轮的事件类型（ADR-0268 §6）。"""

DSH_SURFACE_EVENT_TYPES: frozenset[str] = frozenset({DEVELOPER_MESSAGE_TYPE})
"""DSH 对齐的 session surface 事件类型闭集。"""
