"""Structural domain events → Session spine, with structured log when unbound.

Run 内：``publish_via_session`` → ``Session.append`` → ``*.spine.jsonl``。
Run 外（catalog 创建、Composio OAuth 回调等）：fail-loud 改为
``structlog`` 结构化 INFO，便于 grep debug，不吞异常语义。
"""

from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)


def publish_structural_event(
    *,
    execution_point: str,
    channel: str,
    payload: dict[str, Any],
    producer: type,
) -> Any:
    from lca.plugins.events.publishers._session_publish import publish_via_session
    from lca_kernel.events.errors import MissingPublishSessionError, UnauthorizedPublishError
    from lca_kernel.events.payloads_spine import SpineEventPayload

    sp = SpineEventPayload(
        execution_point=execution_point,
        channel=channel,
        payload=payload,
    )
    try:
        return publish_via_session(sp, producer=producer)
    except MissingPublishSessionError:
        log.info(
            "domain_event.no_session",
            execution_point=execution_point,
            channel=channel,
            payload=payload,
        )
        return None
    except UnauthorizedPublishError as exc:
        log.warning(
            "domain_event.unauthorized",
            execution_point=execution_point,
            error=str(exc),
            payload=payload,
        )
        return None


__all__ = ["publish_structural_event"]
