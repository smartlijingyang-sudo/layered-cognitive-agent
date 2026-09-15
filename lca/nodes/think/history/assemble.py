"""``think.history.assemble`` graph node (spec §D).

Single responsibility: derive the :class:`ModelVisibleRequest` from
:class:`RunSessionWriter` by orphan-dropping dangling tool/result messages.

Mirrors OpenAI Agents SDK's ``drop_orphan_function_calls`` pattern at every
LLM-call preparation step. The orphan-drop lives on
:meth:`RunSessionWriter.derive_messages`; this node is the typed-boundary
adapter that wires the writer into the think subgraph's LLM dispatch port.

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.session.model.context import ModelVisibleRequest
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

if TYPE_CHECKING:
    from lca.contracts.models.core.state.state import AgentState
    from lca.contracts.protocols.session.run_session_writer import (
        RunSessionWriterProtocol,
    )


@dataclass(frozen=True, slots=True)
class HistoryDeriveExecutor:
    """think.history.assemble 节点:writer → :class:`ModelVisibleRequest`."""

    semantic_name: str = "history.derive"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = ("state", "writer")
    declared_outputs: tuple[PortName, ...] = ("model_visible_request",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Resolve declared ports, build the request, return typed output."""
        state = _resolve_port("state", input=input, context=context)
        writer = _resolve_port("writer", input=input, context=context)
        del state
        messages = writer.derive_messages()
        header = writer.request_header()
        system = _system_from_header(header)
        tools: tuple[dict[str, Any], ...] = ()
        return NodeOutput(
            port_values={"model_visible_request": ModelVisibleRequest(
                messages=messages, system=system, tools=tools
            )}
        )


def _resolve_port(
    name: str, *, input: NodeInput, context: NodeContext
) -> Any:
    """Read a declared port from ``input.port_values`` or ``context.runtime``."""
    value = input.port_values.get(name)
    if value is None and hasattr(context, "runtime") and context.runtime is not None:
        # Mirror the think.shortcut convention: runtime is a namespace
        # object; resolve by attribute first, then mapping-style .get.
        value = getattr(context.runtime, name, None)
        if value is None and hasattr(context.runtime, "get"):
            value = context.runtime.get(name)
    if value is None:
        raise TypeError(
            f"history.derive: '{name}' port must be supplied via input.port_values or context.runtime"
        )
    return value


def _system_from_header(header: Any) -> str:
    """Extract the system prompt string from a folded ``EpochHeader``."""
    if header is None:
        return ""
    system = getattr(header, "system", None)
    if isinstance(system, str):
        return system
    return ""


@plugin(
    id="phase.think.history.derive",
    Config=None,
    provides=("phase:think::history.derive",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_history_derive.checked",
                "phase_think_history_derive.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册:``{region}::{semantic_name}``。"""
    del config
    executor = HistoryDeriveExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["HistoryDeriveExecutor", "setup"]
