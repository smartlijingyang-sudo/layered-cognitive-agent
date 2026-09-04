"""`/runs` 载体与运行所有者之间的唯一稳定接缝。

`/runs` 是兼容 HTTP 词汇表，而不是第二套运行模型。无论请求由
Session Spine 还是显式 legacy fixture 执行，carrier 都只依赖本模块的
`RunPort`：创建、控制、查询、诊断和健康投影均由同一 owner 提供。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.core.conversation import ConversationTurn
from lca.plugins.transport.webserver.handlers.runs.doctor import DoctorReport
from lca.plugins.transport.webserver.handlers.runs.observability.identity import AgentRef


@dataclass(frozen=True, slots=True)
class RunRequest:
    """已验证的兼容请求数据，不依赖 Starlette Request 对象。"""

    profile: str
    question: str
    user_text: str
    mode: str
    attachment_ids: tuple[str, ...]
    prior_turns: tuple[ConversationTurn, ...]
    agent: AgentRef
    device_id: str
    plane: str
    extra_plane: str
    execution_target: str
    options: dict[str, Any]
    ctx: object
    assistant_id: str | None = None
    """Optional ADR-0187 §3 D7 one-shot binding for this run (no session
    binding). Non-empty ⇒ run binds to that assistant; ``None`` ⇒ inherit
    legacy default agent (forward-compatible, I-A1)."""


@dataclass(frozen=True, slots=True)
class RunReceipt:
    """创建 run 后返回的稳定标识。"""

    run_id: str
    trace_id: str
    accepted: bool
    rejection_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RunCommandReceipt:
    """不暴露 owner 可变运行状态的稳定命令结果。"""

    accepted: bool
    status: str | None = None
    error: str | None = None
    error_status: int = 404


@runtime_checkable
class RunPort(Protocol):
    """HTTP carrier 可依赖的完整运行词汇表和健康投影。"""

    async def create_and_dispatch(self, request: RunRequest) -> RunReceipt: ...

    async def cancel(self, run_id: str) -> RunCommandReceipt: ...

    async def resume_approval(
        self,
        run_id: str,
        approval_id: str,
        payload: str,
        idempotency_key: str,
    ) -> RunCommandReceipt: ...

    async def summary(self, run_id: str) -> dict[str, Any] | None: ...

    async def stream_chat_completion(
        self, run_id: str, last_seq: int = 0
    ) -> AsyncIterator[bytes]: ...

    async def iter_stamped_events(self, run_id: str, after_seq: int = 0) -> AsyncIterator[Any]: ...

    async def stream_run_live(self, run_id: str, after: int = 0) -> AsyncIterator[bytes]: ...

    async def doctor(self, run_id: str) -> DoctorReport | None: ...

    def journal_path(self, run_id: str) -> Path | None: ...

    def latest_bindings(self) -> object | None: ...

    def stream_process_journal_live(self, last_seq: int = 0) -> AsyncIterator[bytes] | None: ...

    def status_counts(self) -> dict[str, int]: ...

    def live_totals(self) -> dict[str, int]: ...


class RunHealthSource(Protocol):
    """Session Spine 内部委托的最小运行健康事实来源。"""

    def status_counts(self) -> dict[str, int]: ...

    def live_totals(self) -> dict[str, int]: ...


__all__ = [
    "RunCommandReceipt",
    "RunHealthSource",
    "RunPort",
    "RunReceipt",
    "RunRequest",
]
