"""DeltaHandler 与 DeltaHandlerRegistry Protocol（ADR-0074 + ADR-0070）。

``lca/harness/declarative/dispatch.py`` 中的 ``RegistryDeltaReducer``
仅从注入的 ``DeltaHandlerRegistry`` 解析操作，并经唯一 ``Reducer`` seam
折叠状态；它不包含操作分支，也不会静默丢弃未知 delta。

本模块定义两个 Protocol 来约束可插拔 handler 注册表：

- ``DeltaHandler`` — 单个操作的处理单元，签名
  ``apply(state, delta, reducer) -> AgentState``。每个 handler 知道如何
  把一种 ``RunDelta`` 折叠到 state（例如 ``"step"`` / ``"perception"``）。
- ``DeltaHandlerRegistry`` — 以操作名为键注册 / 解析 handler。

runtime 启动时遍历注册表，校验 11 个 Reducer 操作全部有 handler 覆盖，
否则 boot 阶段即报错——不再允许「静默丢弃 delta」。

Reducer-as-Plugin（ADR-0070）：handler 通过 ``ctx.provide`` 注入，profile
bundle 可覆盖默认实现；Reducer 仍是 state mutation 唯一 seam（宪法 C4）。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.act.command_envelope import RunDelta
from lca.contracts.protocols.state.reducer import Reducer


@runtime_checkable
class DeltaHandler(Protocol):
    """处理单个 Reducer delta 操作的可插拔 handler。

    ADR-0074 + ADR-0070：每个实现负责一种操作（例如 ``"step"``、
    ``"perception"``、
    ``"turn"``），通过 ``DeltaHandlerRegistry`` 注册到 runtime。

    注册表保证 Reducer 全部 11 个操作都有对应 handler；未覆盖的操作
    在 boot 阶段报错，不再静默丢弃。
    """

    def apply(self, state: AgentState, delta: RunDelta, reducer: Reducer) -> AgentState:
        """把 ``delta`` 折叠到 ``state``，返回新 AgentState。

        Args:
            state: 当前 AgentState（不可原地修改）。
            delta: 待处理的 RunDelta。
            reducer: Reducer 实例；handler 通过其 ``apply_*`` 方法
                完成 state mutation（宪法 C4）。

        Returns:
            折叠后的新 AgentState。
        """
        ...


@runtime_checkable
class DeltaHandlerRegistry(Protocol):
    """DeltaHandler 注册表：以操作名为键管理 handler。

    runtime 启动时调用 ``resolve(operation)`` 查找 handler；boot 阶段
    校验 11 个 Reducer 操作全部注册，缺失则报错。

    11 个操作（与 ``Reducer`` Protocol 方法一一对应）：

    - ``step`` / ``perception`` / ``turn`` / ``skill_route`` /
      ``activation`` / ``memory`` / ``stop`` / ``error`` / ``resume`` /
      ``artifact_closure`` / ``paused``
    """

    def register(self, operation: str, handler: DeltaHandler) -> None:
        """注册 ``handler`` 处理 ``operation``，并保留其唯一所有权。

        同一 operation 的第二个 handler 必须抛出 ``KeyError``；实现替换应由
        Profile 选择不同 Provider，而不是依赖启动顺序覆盖已有贡献。
        """
        ...

    def resolve(self, operation: str) -> DeltaHandler | None:
        """解析 ``operation`` 对应的 handler；未注册返回 ``None``。"""
        ...

    def registered_delta_operations(self) -> tuple[str, ...]:
        """返回稳定的已注册 Reducer operation 快照，供启动诊断与覆盖校验使用。"""
        ...


__all__ = ["DeltaHandler", "DeltaHandlerRegistry"]
