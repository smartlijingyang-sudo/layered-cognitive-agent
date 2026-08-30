"""EffectHandler 与 EffectHandlerRegistry Protocol（ADR-0074 / ADR-0068）。

ADR-0074 + ADR-0068: Dispatch effects through pluggable handlers.

``lca/harness/declarative/execute/dispatch.py`` owns the registry-backed effect gateway:
it enforces plan policy and idempotency, then delegates every concrete operation
to an ``EffectHandlerRegistry``. New ``CompiledRunPlan`` effect operations are
therefore introduced by registration rather than runtime changes.

本模块引入可插拔的 EffectHandler 注册表机制：
- 每个 ``EffectHandler`` 实现知道如何执行一种 effect 操作（如 ``body.act``、``memory.update``）
- ``EffectHandlerRegistry`` 管理 operation → handler 映射
- ``CompiledRunPlan`` 可声明新 effect 类型而无需修改 runtime 代码

遵循宪法 C4（Reducer 唯一写 State）和双平面架构（认知平面 / 世界平面分离）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lca.contracts.protocols.act.embodiment import Body
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    CommandEnvelope,
    EffectPolicyPlan,
)
from lca.contracts.protocols.memory.memory import MemorySystem


@runtime_checkable
class EffectCapabilities(Protocol):
    """Minimal capability facade visible behind the effect execution seam."""

    @property
    def body(self) -> Body: ...

    @property
    def memory(self) -> MemorySystem: ...


@runtime_checkable
class EffectHandler(Protocol):
    """Handle a specific effect operation.

    Each handler knows how to execute one effect operation (e.g., "body.act", "memory.update").
    The registry-backed gateway dispatches to handlers without operation branches,
    so CompiledRunPlan can declare new effect types without modifying runtime.

    实现示例：
    - ``BodyActEffectHandler``: 处理 ``body.act`` 操作，调用 ``SafeExecutor``
    - ``MemoryUpdateEffectHandler``: 处理 ``memory.update`` 操作，调用 ``MemoryWriter``
    - 自定义 handler: 插件可通过注册表注入新的 effect 类型

    注意：所有 state mutation 必须经 ``Reducer`` 返回新 state（宪法 C4），
    handler 本身不直接修改 ``AgentState``。实现可以通过 ``receipt_name``
    声明 operation-specific 的稳定收据标签；gateway 不维护 operation 分支。
    """

    async def handle(
        self,
        envelope: CommandEnvelope,
        policy: EffectPolicyPlan,
        capabilities: EffectCapabilities,
    ) -> Any:
        """Execute the effect operation.

        Args:
            envelope: 命令信封，包含 effect 操作的具体参数
            policy: effect 策略计划，声明允许的操作和约束
            capabilities: runtime phase 能力 facade（``RuntimePhaseCapabilities``），
                         包含 brain / body / memory / perceive_hub / stop_rule

        Returns:
            effect 执行结果（具体类型由实现决定）

        Raises:
            DeclarativeValidationError: 当 policy 不允许该操作时
            Exception: 当 effect 执行失败时
        """
        ...


@runtime_checkable
class EffectHandlerRegistry(Protocol):
    """Registry of EffectHandler implementations.

    ADR-0074: registry-backed dispatch resolves only registered handlers.
    Runtime 启动时注册默认 handler（``body.act`` / ``memory.update``），
    插件可通过 ``ctx.provide("effect_handler_registry", ...)`` 注入扩展。

    典型用法：
    ```python
    registry = ctx.inject("effect_handler_registry")
    handler = registry.resolve("body.act")
    if handler is None:
        raise DeclarativeValidationError("E001", f"Unknown effect operation: body.act")
    result = await handler.handle(envelope, policy, capabilities)
    ```
    """

    def register(self, operation: str, handler: EffectHandler) -> None:
        """Register a handler for the given operation and preserve unique ownership.

        Args:
            operation: effect 操作名（如 ``"body.act"``、``"memory.update"``）
            handler: 处理该操作的 EffectHandler 实现

        Raises:
            KeyError: 当同一 operation 已有 handler 所有者时。
            ValueError: 当 operation 为空或不是字符串时。
        """
        ...

    def resolve(self, operation: str) -> EffectHandler | None:
        """Resolve handler for operation, or None if not registered.

        Args:
            operation: effect 操作名

        Returns:
            对应的 EffectHandler，或 ``None``（当未注册时）

        Note:
            Runtime 应在 resolve 返回 ``None`` 时抛出 ``DeclarativeValidationError``，
            而非静默跳过（fail-fast 原则）。
        """
        ...

    def registered_effect_operations(self) -> tuple[str, ...]:
        """返回稳定的已注册 effect operation 快照，供启动诊断与覆盖校验使用。"""
        ...


__all__ = ["EffectCapabilities", "EffectHandler", "EffectHandlerRegistry"]
