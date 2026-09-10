"""NodeExecutor Protocol — think 子图节点通用化接口。

ADR-0217 §3.3 + ADR-0219 §5.5(typed port contract 挂在 plugin 自身)。

职责边界:
- 本协议**只服务 think 子图**(`bundles/think.yaml`);perceive / act / reflect /
  remember / stop 仍走 `PhaseExecutor.execute(context, input) -> PhaseResult`,
  本模块不替代。
- 节点 plugin 自报 `declared_inputs` / `declared_outputs`(typed `PortName`
  闭集)。**图层(``BundleGraphNode`` / driver)不持有 port 字段名** —
  图只懂拓扑,plugin 自己懂 port contract。详见 ADR-0219 §5.5「图不知道
  业务,业务不知道图」。
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

from lca.contracts.protocols.declarative.declarative_1.ports import PortName


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
    """节点输入。

    `port_values` 是 driver 投影后的 typed dict:key 来自
    ``executor.declared_inputs``,value 来自 `PortRegistry._ports`。
    缺 port 不报错,填空 dict;plugin 自己处理空值。
    """

    __slots__ = ("port_values",)

    def __init__(self, port_values: Mapping[PortName, Any]) -> None:
        self.port_values = dict(port_values)


class NodeOutput:
    """节点输出。

    `port_values` 是 plugin 自己声明的输出 port 集合(driver 用
    ``executor.declared_outputs`` 校验完整性,不在 driver 读 `node.outputs`)。
    """

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
    """think 子图节点 plugin 必须实现的协议。

    协议字段:
        semantic_name: 唯一标识,等于 yaml `factory:` 字符串(如 `think.reason`)。
            `FactoryResolver` 按 (semantic_name, region) 二元组命中。
        declared_inputs / declared_outputs: typed port contract,plugin 自报。
            必须全部 ∈ `PortName` Literal 闭集;driver 投影 `PortRegistry._ports`
            → `NodeInput.port_values` 时只取 `declared_inputs` 里有的 key,
            driver 校验 `NodeOutput.port_values` 的 key ⊆ `declared_outputs`。
            bundle yaml 不再写 `inputs:` / `outputs:` 字段(ADR-0219 §5.5)。

    协议方法:
        execute: 接收 NodeContext + NodeInput,返回 NodeOutput。plugin 不感知
            phase、不感知 graph、不感知 outer plan_ref。

    实现要求:
        - 纯函数式为佳(无 module-level 状态);如需状态,通过 NodeContext.runtime
            注入,不要自己 `from_env` / 单例。
        - 失败抛标准 Exception;不要 catch 后吞。
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