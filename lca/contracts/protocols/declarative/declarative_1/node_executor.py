"""NodeExecutor Protocol — think 子图节点通用化接口。

ADR-0217 §3.3。

职责边界:
- 本协议**只服务 think 子图**(`bundles/think.yaml`);perceive / act / reflect /
  remember / stop 仍走 `PhaseExecutor.execute(context, input) -> PhaseResult`,
  本模块不替代。
- 节点 plugin 不感知 phase、不感知 graph,只接 `NodeInput.port_values` 字典,
  吐 `NodeOutput.port_values` 字典。框架负责端口投影、when 路由、嵌套递归。
- 失败表达:plugin 抛标准 Exception,框架 catch 后映射为 `node_failure`,
  而不是 `PhaseErrorKind` 枚举。

为什么独立 Protocol(不扩展 PhaseExecutor):
- PhaseExecutor 是 18 个 plugin(6 phase + 12 control)共用入口,职责是
  "phase 级执行 + phase 级决策收口";
- NodeExecutor 是 think 子图"业务节点"专用,职责是"按 yaml 声明的 ports
  做局部工作" — 两个职责不可合并。
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable


class NodeContext:
    """节点级执行上下文。框架注入,plugin 只读。

    Attributes:
        runtime: 框架提供的执行器子集(LlmResolver / MemoryRead / 等),
            由 framework 在 interpreter 启动时按 plugin 声明装配。
        budget: yaml `config:` 投影的图级参数(max_visits / cooldown_ms 等)。
        metadata: 只读视图,包含节点 purpose、subgraph metadata、trace 标签。
    """

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

    def __init__(self, port_values: Mapping[str, Any]) -> None:
        self.port_values = dict(port_values)


class NodeOutput:
    """节点输出。"""

    __slots__ = ("port_values", "next_hint")

    def __init__(
        self,
        port_values: Mapping[str, Any],
        next_hint: str | None = None,
    ) -> None:
        self.port_values = dict(port_values)
        self.next_hint = next_hint


@runtime_checkable
class NodeExecutor(Protocol):
    """think 子图节点 plugin 必须实现的协议。

    协议字段:
        semantic_name: 唯一标识,等于 yaml `factory:` 字符串(如 `think.reason`)。
            `FactoryResolver` 按 (semantic_name, region) 二元组命中。

    协议方法:
        execute: 接收 NodeContext + NodeInput,返回 NodeOutput。plugin 不感知
            phase、不感知 graph、不感知 outer plan_ref。

    实现要求:
        - 纯函数式为佳(无 module-level 状态);如需状态,通过 NodeContext.runtime
            注入,不要自己 `from_env` / 单例。
        - 失败抛标准 Exception;不要 catch 后吞。
    """

    semantic_name: str

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
