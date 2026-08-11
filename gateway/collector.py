"""Gateway 专用 ObservabilityHub —— SSE + jsonl 双投影。"""

from __future__ import annotations

from pathlib import Path

from lca.layer0_infra.observability import ObservabilityHub
from lca.layer0_infra.observability.journal.jsonl_projector import JsonlJournalProjector
from lca.layer0_infra.observability.journal.sse_projector import EmitFn, SSEJournalProjector
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity
from lca.layer0_infra.observability.settings import ObservabilitySettings


def _noop_emit(_frame: str | None) -> None:
    pass


_NOOP_EMIT: EmitFn = _noop_emit


class GatewayCollector(ObservabilityHub):
    """SSE 广播 + jsonl 落盘，作为 Team/Agent 的可观测性后端。

    支持两阶段初始化：先 ``GatewayCollector(jsonl_path)`` 创建实例，
    再通过 ``bind_emit(session.emit)`` 绑定 SSE 回调，打破
    session ↔ hub 的循环依赖（消除 ``list[None]`` 闭包反模式）。
    """

    def __init__(
        self,
        jsonl_path: Path,
        *,
        emit: EmitFn | None = None,
        verbosity: Verbosity | None = None,
    ) -> None:
        resolved = verbosity if verbosity is not None else ObservabilitySettings().verbosity
        self._jsonl_projector = JsonlJournalProjector(jsonl_path)
        self._sse_projector = SSEJournalProjector(emit if emit is not None else _NOOP_EMIT)
        super().__init__(
            [],
            policy=AttributePolicy(resolved),
            journal_projectors=[
                self._sse_projector,
                self._jsonl_projector,
            ],
        )

    def bind_emit(self, emit: EmitFn) -> None:
        """Late-bind the SSE emit callback (breaks session ↔ hub cycle)."""
        self._sse_projector._emit = emit
