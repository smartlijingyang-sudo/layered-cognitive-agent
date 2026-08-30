"""ActionHandler Provider plugin — Tier-2 (ADR-0074).

Migrates hard-coded `_operation_for()` logic from `action_catalog.py` into
pluggable ActionHandler implementations. Each handler knows how to create
an Action for a specific ActionType (e.g., "respond", "use_tool").

New action types = register a new handler, no core code changes required.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import ACTION_HANDLERS, TOOL_BATCH_EXECUTION_POLICY
from lca.contracts.protocols import SafeExecutor, ToolRegistry, TransportRegistryProtocol
from lca.contracts.protocols.act.action import Action
from lca.contracts.protocols.act.action_handler import ActionHandler, ActionHandlerRegistry
from lca.contracts.protocols.act.tool_batch_execution import ToolBatchExecutionPolicy
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.handler_registry import UniqueOperationRegistry


class Config(BaseModel):
    """Configuration for action handler provider plugin."""

    model_config = {"extra": "forbid"}


class RespondActionHandler(ActionHandler):
    """Handler for respond action type (ADR-0074).

    Creates RespondOperation instances that handle direct text responses.
    """

    def create(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistryProtocol,
    ) -> Action | None:
        """Create a RespondOperation instance.

        Args:
            tool_registry: Tool registry (unused for respond).
            safe_executor: Safe executor (unused for respond).
            transport_registry: Transport registry (unused for respond).

        Returns:
            RespondOperation instance.
        """
        from lca.cognition.body.action_handlers import RespondOperation

        return RespondOperation()


class StopActionHandler(ActionHandler):
    """Handler for the terminal stop action."""

    def create(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistryProtocol,
    ) -> Action | None:
        del tool_registry, safe_executor, transport_registry
        from lca.cognition.body.action_handlers import TerminalOperation

        return TerminalOperation()


class AskHumanActionHandler(ActionHandler):
    """Handler for the explicit human-input terminal action."""

    def create(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistryProtocol,
    ) -> Action | None:
        del tool_registry, safe_executor, transport_registry
        from lca.cognition.body.action_handlers import AskHumanOperation

        return AskHumanOperation()


class UseToolActionHandler(ActionHandler):
    """Handler for use_tool action type with Profile-owned batch scheduling."""

    def __init__(self, batch_execution_policy: ToolBatchExecutionPolicy) -> None:
        """Require the policy selected by the active Profile.

        Choosing a scheduling policy changes execution semantics. The production
        handler therefore never materializes a concrete fallback; callers must
        make the policy boundary explicit. ``DefaultActionHandlerRegistry``
        retains the legacy safe default only as an isolated compatibility facade.
        """

        if not isinstance(batch_execution_policy, ToolBatchExecutionPolicy):
            raise TypeError("batch_execution_policy must implement ToolBatchExecutionPolicy")
        self._batch_execution_policy = batch_execution_policy

    def create(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistryProtocol,
    ) -> Action | None:
        """Create a UseToolOperation instance.

        Args:
            tool_registry: Tool registry for tool lookup.
            safe_executor: Safe executor for controlled tool execution.
            transport_registry: Transport registry (unused for use_tool).

        Returns:
            UseToolOperation instance.
        """
        from lca.cognition.body.action_handlers import UseToolOperation

        return UseToolOperation(
            tool_registry,
            safe_executor,
            batch_execution_policy=self._batch_execution_policy,
        )


class DelegateActionHandler(ActionHandler):
    """Handler for delegate action type (ADR-0074).

    Creates DelegateOperation instances that handle task delegation to
    team members with single-target blocking or multi-target fan-out.
    """

    def create(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistryProtocol,
    ) -> Action | None:
        """Create a DelegateOperation instance.

        Args:
            tool_registry: Tool registry (unused for delegate).
            safe_executor: Safe executor (unused for delegate).
            transport_registry: Transport registry for agent communication.

        Returns:
            DelegateOperation instance.
        """
        from lca.cognition.body.action_handlers import DelegateOperation

        return DelegateOperation(transport_registry)


class HandoffActionHandler(ActionHandler):
    """Handler for handoff action type (ADR-0074).

    Creates HandoffOperation instances that handle non-blocking control
    transfer to other agents (fire-and-forget pattern).
    """

    def create(
        self,
        tool_registry: ToolRegistry,
        safe_executor: SafeExecutor,
        transport_registry: TransportRegistryProtocol,
    ) -> Action | None:
        """Create a HandoffOperation instance.

        Args:
            tool_registry: Tool registry (unused for handoff).
            safe_executor: Safe executor (unused for handoff).
            transport_registry: Transport registry for agent communication.

        Returns:
            HandoffOperation instance.
        """
        from lca.cognition.body.action_handlers import HandoffOperation

        return HandoffOperation(transport_registry)


class InMemoryActionHandlerRegistry(UniqueOperationRegistry[ActionHandler], ActionHandlerRegistry):
    """动作处理器接缝的中性容器。

    默认行为仍由 :func:`register_default_action_handlers` 在 Provider 中安装；
    共享注册表确保同一个 ActionType 不会被后启动的 Provider 静默覆盖。
    """

    def __init__(self) -> None:
        super().__init__("action handler")

    def register(self, action_type: str, handler: ActionHandler) -> None:
        """注册一个 ActionType 的唯一 handler 所有者。"""
        self._register(action_type, handler)

    def resolve(self, action_type: str) -> ActionHandler | None:
        """解析 ActionType 对应的 handler。"""
        return self._resolve(action_type)

    def registered(self) -> tuple[str, ...]:
        """返回稳定的已注册 ActionType 快照。"""
        return cast("tuple[str, ...]", self._registered_operations())


def register_default_action_handlers(
    registry: ActionHandlerRegistry,
    *,
    batch_execution_policy: ToolBatchExecutionPolicy,
) -> None:
    """Install the closed action set with one explicit tool-batch policy."""
    from lca.contracts.atoms.enums import ActionType

    defaults = (
        (ActionType.RESPOND.value, RespondActionHandler()),
        (
            ActionType.USE_TOOL.value,
            UseToolActionHandler(batch_execution_policy=batch_execution_policy),
        ),
        (ActionType.DELEGATE.value, DelegateActionHandler()),
        (ActionType.HANDOFF.value, HandoffActionHandler()),
        (ActionType.STOP.value, StopActionHandler()),
        (ActionType.ASK_HUMAN.value, AskHumanActionHandler()),
    )
    for action_type, handler in defaults:
        registry.register(action_type, handler)


class DefaultActionHandlerRegistry(InMemoryActionHandlerRegistry):
    """Compatibility factory for a registry populated with built-in handlers.

    Production profiles must use ``lca-action-handler-provider`` and inject a
    selected ``ToolBatchExecutionPolicy``. This facade preserves the historical
    in-process constructor for tests and legacy callers, making its safe default
    explicit instead of allowing ``UseToolActionHandler`` to select one.
    """

    def __init__(self, batch_execution_policy: ToolBatchExecutionPolicy | None = None) -> None:
        super().__init__()
        register_default_action_handlers(
            self,
            batch_execution_policy=batch_execution_policy or _compatibility_safe_batch_policy(),
        )


def _compatibility_safe_batch_policy() -> ToolBatchExecutionPolicy:
    """Return the explicit legacy default used only by the compatibility facade."""

    from lca.cognition.body.tool_batch_execution import SafeToolBatchExecutionPolicy

    return SafeToolBatchExecutionPolicy()


@plugin(
    id="lca-action-handler-provider",
    requires=[ACTION_HANDLERS.key, TOOL_BATCH_EXECUTION_POLICY.key],
    implements=[ActionHandlerRegistry],
    layer="L1",
    effects="none",
    description="Provide the default ActionHandler implementations (4 handlers for RESPOND/USE_TOOL/DELEGATE/HANDOFF).",
    kind=PluginKind.PROVIDER,
    test_suite="tests/test_plugin_alignment.py::test_tier2_plugin_shape",
    functional_group=FunctionalGroup.G7_EXECUTION,
    logic_address=LogicAddress(
        functional_group=FunctionalGroup.G7_EXECUTION,
        control_slot=ControlSlot.ACT_EXECUTE,
        scope=Scope.AGENT,
        authority=(ACTION_HANDLERS.key, TOOL_BATCH_EXECUTION_POLICY.key),
        evidence=("action.handler.registered",),
        revision="v1",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Register default action handlers for the closed action set.

    Injects the ActionHandlerRegistry from the seam and registers handlers for
    all six built-in action types.

    Args:
        ctx: Plugin context for capability injection.
        config: Plugin configuration (unused for default handlers).
    """
    registry: ActionHandlerRegistry = ctx.require(ACTION_HANDLERS.key)
    batch_execution_policy = ctx.require(TOOL_BATCH_EXECUTION_POLICY.key)
    if not isinstance(batch_execution_policy, ToolBatchExecutionPolicy):
        raise TypeError("tool_batch_execution_policy must implement ToolBatchExecutionPolicy")
    register_default_action_handlers(registry, batch_execution_policy=batch_execution_policy)


__all__ = [
    "AskHumanActionHandler",
    "DefaultActionHandlerRegistry",
    "DelegateActionHandler",
    "HandoffActionHandler",
    "InMemoryActionHandlerRegistry",
    "RespondActionHandler",
    "StopActionHandler",
    "UseToolActionHandler",
    "register_default_action_handlers",
    "setup",
]
