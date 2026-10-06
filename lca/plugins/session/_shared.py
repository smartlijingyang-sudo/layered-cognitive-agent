"""session 域 plugin 共享接线小件（ADR-0195）。

收敛点：挂到 SessionStore 的五个 plugin（projection_cache /
projection_registry / spine_anomaly / telemetry_capture / title_service）
原来各有一份字符级相同的 ``add_observer_hook`` fail-loud 守卫，
收敛到 :func:`require_observer_hook`，fail-loud 契约单点定义。
"""

from collections.abc import Callable
from typing import Any


def require_observer_hook(store: Any) -> Callable[..., Any]:
    """取 ``store.add_observer_hook``；缺失则 ``TypeError`` fail-loud。

    语义与原先五处内联守卫逐字一致（含错误消息文本）。
    """
    hook = getattr(store, "add_observer_hook", None)
    if not callable(hook):
        msg = f"SessionStore 必须提供 add_observer_hook;got {type(store).__name__} without it"
        raise TypeError(msg)
    return hook
