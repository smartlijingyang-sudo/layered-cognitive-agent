"""session 域 plugin 共享接线小件（ADR-0195）。

收敛点：挂到 SessionStore 的五个 plugin（projection_cache /
projection_registry / spine_anomaly / telemetry_capture / title_service）
原来各有一份字符级相同的 ``add_observer_hook`` fail-loud 守卫，
收敛到 :func:`require_observer_hook`，fail-loud 契约单点定义。
"""

from collections.abc import Callable
from typing import Any

from lca_kernel.events.session.session import SessionEvent

TURN_ENDED = "turn.ended.v1"
"""journal 事件类型：turn 结束。

四处 session plugin（projection_cache / session_stats /
session_turn_control / session_turn_outline）原来各有一份字符级相同的
私有 ``_TURN_ENDED`` 常量，收敛到此，语义逐字一致。
"""


def require_observer_hook(store: Any) -> Callable[..., Any]:
    """取 ``store.add_observer_hook``；缺失则 ``TypeError`` fail-loud。

    语义与原先五处内联守卫逐字一致（含错误消息文本）。
    """
    hook = getattr(store, "add_observer_hook", None)
    if not callable(hook):
        msg = f"SessionStore 必须提供 add_observer_hook;got {type(store).__name__} without it"
        raise TypeError(msg)
    return hook


def session_id_of(session: Any) -> str:
    """从 Session 实例派生 session id；缺 ``.id`` 回退 ``"unknown"``。

    Session 协议保证 :attr:`Session.id` 权威（与 ``persistence_jsonl``
    的 Session 实例权威规则一致）。
    """
    sid = getattr(session, "id", None)
    if isinstance(sid, str) and sid:
        return sid
    return "unknown"


def turn_of(event: SessionEvent) -> int | None:
    """事件 payload 的非负整数 ``turn``；缺失 / 非法返回 ``None``。"""
    turn = event.data.get("turn")
    if isinstance(turn, int) and not isinstance(turn, bool) and turn >= 0:
        return turn
    return None
