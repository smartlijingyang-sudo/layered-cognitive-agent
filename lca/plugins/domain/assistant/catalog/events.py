"""Catalog 事件发射 mixin。

``_AssistantCatalogImpl`` 的 EP 发射 helpers 拆出为本 mixin：无 emitter 时仅
log（PR-3 单元测试路径），有 emitter 时走注入的 audited ``ctx.emit``。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import structlog

from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_CREATED,
    ASSISTANT_PROFILE_REVISED,
)
from lca.plugins.assistant.events._events import (
    AssistantBootstrapCompletedEventPayload,
    AssistantCreatedEventPayload,
    AssistantProfileRevisedEventPayload,
)

log = structlog.get_logger(__name__)


class _AssistantCatalogEventsMixin:
    """EP 发射 helpers;无 emitter 时仅 log(PR-3 单元测试路径)。"""

    _emit: Callable[[str, Mapping[str, Any]], Any] | None

    def _emit_created(self, payload: AssistantCreatedEventPayload) -> None:
        """发 ``assistant.created`` EP;无 emitter 时仅 log。"""
        if self._emit is None:
            log.info(
                "assistant.catalog.ep.no_emitter",
                ep=ASSISTANT_CREATED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_CREATED, payload.to_dict())

    def _emit_bootstrap_completed(self, payload: AssistantBootstrapCompletedEventPayload) -> None:
        """发 ``assistant.bootstrap.completed`` EP;无 emitter 时仅 log。"""
        if self._emit is None:
            log.info(
                "assistant.catalog.ep.no_emitter",
                ep=ASSISTANT_BOOTSTRAP_COMPLETED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_BOOTSTRAP_COMPLETED, payload.to_dict())

    def _emit_profile_revised(self, payload: AssistantProfileRevisedEventPayload) -> None:
        """发 ``assistant.profile.revised`` EP;无 emitter 时仅 log。"""
        if self._emit is None:
            log.info(
                "assistant.catalog.ep.no_emitter",
                ep=ASSISTANT_PROFILE_REVISED,
                payload=payload.to_dict(),
            )
            return
        self._emit(ASSISTANT_PROFILE_REVISED, payload.to_dict())
