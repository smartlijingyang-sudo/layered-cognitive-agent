"""L3 团队编排协议 —— 策略 / 上下文 / 共享记忆 / 聚合。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from lca.contracts.memory import MemoryRecord
from lca.contracts.protocols.agent import AgentEntrypoint
from lca.contracts.protocols.infra import AgentTransport
from lca.contracts.result import Result
from lca.contracts.role_team import TeamConfig
from lca.contracts.team_progress import DelegationLedgerProtocol


@runtime_checkable
class SupervisorProtocol(Protocol):
    """Supervisor 最小接口 —— contracts 层不依赖 L3 具体类。"""

    async def execute(self, task: str) -> Result: ...
    def bind_team(self, transport: AgentTransport, roster_desc: str) -> None: ...
    def configure_runtime(self, **capabilities: Any) -> None: ...
    def register_hook(self, hook_name: str, hook_fn: Any) -> None: ...
    def wrap_brain_component(self, name: str, wrapper: Any) -> None: ...


@dataclass
class OrchestrationContext:
    """编排策略的运行时上下文，由 TeamOrchestrator 构造并传给策略实例。"""

    members: Sequence[AgentEntrypoint] = field(default_factory=list)
    config: TeamConfig | None = None
    supervisor: SupervisorProtocol | None = None
    transport: AgentTransport | None = None
    roster_desc: str = ""
    ledger_factory: Callable[[frozenset[str]], DelegationLedgerProtocol] | None = None
    team_id: str = ""
    shared_memory: SharedMemoryStore | None = None


@runtime_checkable
class OrchestrationStrategy(Protocol):
    """编排策略接口：每种 process 模式对应一个实现。"""

    async def run(self, context: OrchestrationContext, objective: str) -> Result: ...


@runtime_checkable
class SharedMemoryStore(Protocol):
    """跨 Agent 共享记忆存储接口。

    按 layer 分流读写（CoALA：semantic/procedural 可共享，
    episodic/working 保持私有）。由 TeamOrchestrator 构造并注入。
    """

    def is_shared(self, layer: str) -> bool: ...
    def add_record(self, layer: str, record: MemoryRecord) -> None: ...
    def get_records(self, layer: str) -> list[MemoryRecord]: ...


@runtime_checkable
class Synthesizer(Protocol):
    """MoA 聚合器：将多个并行候选结果合成为一个最终结果。"""

    async def synthesize(self, objective: str, candidates: list[Result]) -> Result: ...
