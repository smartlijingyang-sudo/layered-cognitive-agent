"""NodeExecutor Protocol — 唯一 phase / think / act 节点协议。

ADR-0221: ``NodeExecutor`` is the sole node protocol. Every phase /
think / act / control node plugin implements it directly; the legacy
``PhaseExecutor`` protocol has been retired.

职责边界:
- 节点 plugin 自报 `declared_inputs` / `declared_outputs`(typed `PortName`
  闭集)。**图层(``BundleGraphNode`` / driver)不持有 port 字段名** —
  图只懂拓扑,plugin 自己懂 port contract。详见 ADR-0219 §5.5「图不知道
  业务,业务不知道图」。
- 失败表达:plugin 抛标准 Exception,框架 catch 后映射为 `node_failure`,
  不再有 PhaseResult / PhaseErrorKind 枚举。
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from lca.contracts.protocols.declarative.declarative_1.ports import PortName


class NodeContext:
    """节点级执行上下文。框架注入,plugin 只读。"""

    __slots__ = ("runtime", "budget", "metadata")

    def __init__(
        self,
        *,
        runtime: Mapping[str, Any],
        budget: Mapping[str, Any],
        metadata: Mapping[str, Any],
    ) -> None:
        self.runtime = runtime
        self.budget = budget
        self.metadata = metadata


class NodeInput:
    """节点输入。"""

    __slots__ = ("port_values",)

    def __init__(self, port_values: Mapping[PortName, Any]) -> None:
        self.port_values = dict(port_values)


class NodeOutput:
    """节点输出。"""

    __slots__ = ("port_values", "next_hint")

    def __init__(
        self,
        port_values: Mapping[PortName, Any],
        next_hint: str | None = None,
    ) -> None:
        self.port_values = dict(port_values)
        self.next_hint = next_hint


@runtime_checkable
class NodeExecutor(Protocol):
    """唯一的节点协议。

    协议字段:
        semantic_name: 唯一标识,等于 yaml `factory:` 字符串(如 `phase.perceive.observe`)。
        declared_inputs / declared_outputs: typed port contract,plugin 自报。

    协议方法:
        execute: 接收 NodeContext + NodeInput,返回 NodeOutput。plugin 不感知
            phase、不感知 graph、不感知 outer plan_ref。
    """

    semantic_name: str
    declared_inputs: tuple[PortName, ...]
    declared_outputs: tuple[PortName, ...]

    async def execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput: ...


__all__ = [
    "NodeContext",
    "NodeExecutor",
    "NodeInput",
    "NodeOutput",
]