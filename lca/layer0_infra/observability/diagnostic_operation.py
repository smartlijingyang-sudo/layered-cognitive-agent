"""诊断操作的开始、完成、失败与耗时记录实现。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Literal

from lca.contracts.models.observability.diagnostic import DiagnosticCategory, DiagnosticStatus


class DiagnosticOperation:
    """同步操作诊断句柄；异常不被吞没。"""

    def __init__(
        self,
        hub: Any,
        *,
        category: DiagnosticCategory | str,
        operation: str,
        plugin: str,
        attributes: dict[str, Any],
        causation_refs: tuple[str, ...],
        actor_role: Callable[[], str],
        actor_step: Callable[[], int | None],
    ) -> None:
        self._hub = hub
        self._category = DiagnosticCategory(category)
        self._operation = operation
        self._plugin = plugin
        self._attributes = attributes
        self._causation_refs = causation_refs
        self._actor_role = actor_role
        self._actor_step = actor_step
        self._output: dict[str, Any] = {}
        self._started = 0.0

    def set_output(self, **output: Any) -> None:
        """在完成前补充结果摘要。"""
        self._output.update(output)

    def __enter__(self) -> DiagnosticOperation:
        self._started = time.perf_counter()
        self._emit(DiagnosticStatus.STARTED)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _tb: Any,
    ) -> Literal[False]:
        duration_ms = int((time.perf_counter() - self._started) * 1000) if self._started else 0
        if exc is None:
            self._emit(DiagnosticStatus.SUCCEEDED, duration_ms=duration_ms)
        else:
            self._emit(
                DiagnosticStatus.FAILED,
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
        return False

    def _emit(
        self,
        status: DiagnosticStatus,
        *,
        duration_ms: int | None = None,
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        if self._hub is None:
            return
        self._hub.emit_diagnostic(
            category=self._category,
            operation=self._operation,
            plugin=self._plugin,
            status=status,
            attributes=self._attributes,
            output=self._output,
            duration_ms=duration_ms,
            error_type=error_type,
            error_message=error_message,
            causation_refs=self._causation_refs,
            actor_role=self._actor_role(),
            actor_step=self._actor_step(),
        )


__all__ = ["DiagnosticOperation"]
