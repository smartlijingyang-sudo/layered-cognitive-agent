"""Shared observation / diagnosis plugin plumbing.

Consolidates the ``_now_iso`` / ``_OBSERVER_ACTOR`` / fact-envelope boilerplate
that was copied across the observation and diagnosis plugins. Plugins keep
their projection logic and pass only the event-specific payload; the envelope
(``publish_ep_bound`` or ``append_catalog_bound``) and the UTC timestamp live
here so the 13 copies cannot drift.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.ids.ids import utc_now_iso
from lca.loop.fact_gateway import append_catalog_bound, publish_ep_bound

OBSERVER_ACTOR = "observation"


def now_iso() -> str:
    """ISO-8601 UTC 时间字符串（观察事实时间戳统一格式）。"""
    return utc_now_iso()


def publish_ep_observation(
    event: str,
    payload: dict[str, Any],
    *,
    actor: str = OBSERVER_ACTOR,
) -> None:
    """经 ``publish_ep_bound`` 发布 spine EP 观察事实。"""
    publish_ep_bound(event, payload, actor=actor)


def publish_session_observation(
    fact: Any,
    *,
    session: object | None,
    actor: str = OBSERVER_ACTOR,
) -> None:
    """经 ``append_catalog_bound`` 发布 Session 单轨观察事实。

    ``session`` 由调用方注入（``current_session()``），保持依赖方向：
    本模块不反向 import 插件层的 session 定位器。
    """
    append_catalog_bound(fact, session=session, actor=actor)


__all__ = [
    "OBSERVER_ACTOR",
    "now_iso",
    "publish_ep_observation",
    "publish_session_observation",
]
