"""session 域 plugin 共享接线小件（ADR-0195）。

收敛点：挂到 SessionStore 的五个 plugin（projection_cache /
projection_registry / spine_anomaly / telemetry_capture / title_service）
原来各有一份字符级相同的 ``add_observer_hook`` fail-loud 守卫，
收敛到 :func:`require_observer_hook`，fail-loud 契约单点定义。

收敛点：同一五 plugin 的 store-observer attach ritual（现存 Session 逐个
挂入，单 session 失败 contained → fail-loud 守卫 → ``add_observer_hook``
接管未来 create/restore → cancel 存 ``_store_hooks``）收敛到
:func:`attach_store_observers`（RA-019）。canonical 顺序 require-first：
先 :func:`require_observer_hook` 再遍历现存 Session——钩子缺失时零部分
挂入（其余四家原先 list-first，会留下半接线状态）。
"""

from collections.abc import Callable
from typing import Any, cast

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


def attach_store_observers(
    store: Any,
    attach_one: Callable[[Any], None],
    hooks_sink: list[Callable[[], None]] | None = None,
) -> None:
    """Canonical store-observer attach ritual（RA-019）。

    五 session plugin（projection_cache / projection_registry /
    spine_anomaly / telemetry_capture / title_service）原来各写一遍的
    ritual 收敛到此。``attach_one`` 负责单个 Session 的挂入与 fail-soft
    contained（DSH 对齐的文档化选择）；缺 ``add_observer_hook`` 时抛
    ``TypeError`` fail-loud。

    Canonical 顺序（本轮裁定，覆盖原先的两派分歧）：**require-first**——
    先 :func:`require_observer_hook` fail-loud，再遍历现存 Session。
    title_service 本来就是这个顺序；其余四家原先 list-first，改后钩子缺失
    时零部分挂入（原来会先挂完现存 Session 再抛，留下半接线状态）。
    ``attach_one`` 同时用作未来 create/restore 的钩子回调；钩子反注册闭包
    存入 ``hooks_sink``（spine_anomaly / projection_registry 等无
    ``_store_hooks`` 的 plugin 传 ``None`` 即丢弃）。
    """
    hook = require_observer_hook(store)
    for session in getattr(store, "list", lambda: ())():
        attach_one(session)
    cancel = hook(attach_one)
    if callable(cancel) and hooks_sink is not None:
        hooks_sink.append(cast("Callable[[], None]", cancel))
