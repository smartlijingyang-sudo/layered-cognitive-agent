"""``think.llm.persist`` graph node (PR-B single-responsibility split).

Single responsibility: write the LLM result to the Session via
``RunSessionWriterProtocol`` (spec §C persist-before-execute invariant).

Reads :class:`LLMResponse` + the bound writer + the current step from
typed ports and forwards a typed ``journaled`` boolean confirming the
journal write happened. Does NOT call the adapter — that lives in the
sibling ``think.llm.invoke`` node.

Pair shape (PR-B):

- ``think.llm.invoke`` (sibling): typed ports → adapter call
- ``think.llm.persist`` (this node): response → writer.append_*

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.session.run_session_writer import (
    RunSessionWriterProtocol,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


@dataclass(frozen=True, slots=True)
class LlmPersistExecutor:
    """think.llm.persist 节点: ``LLMResponse`` → ``writer.append_*`` → ``journaled``."""

    semantic_name: str = "llm.persist"
    region: str = "think"
    # Runtime-carrier reads for ``state`` + ``writer``; the rest of the
    # think subgraph uses the same pattern.
    declared_inputs: tuple[PortName, ...] = ("llm_response",)
    declared_outputs: tuple[PortName, ...] = ("journaled",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Persist the assistant message + tool calls to the Session.

        ``step``/``turn`` derive from the ``state`` kernel carrier
        (the old single node used ``state.step`` for both writer rows).
        ``adapter`` is NOT in the port set — that path lives in the
        sibling ``think.llm.invoke``.
        """
        state = _resolve_state(context=context)
        writer = _resolve_writer(context=context)
        response = _resolve_port("llm_response", input=input)
        step = int(getattr(state, "step", 0) or 0)
        _persist_assistant(writer=writer, response=response, step=step)
        return NodeOutput(port_values={"journaled": True})


def _persist_assistant(
    *,
    writer: RunSessionWriterProtocol,
    response: LLMResponse,
    step: int,
) -> None:
    """Write the assistant row + per-tool-call rows to the Session.

    ``surface/assistant_message`` carries the model text + tool_calls
    array; ``log/tool_call`` carries one row per call so trace /
    metrics projections can join on ``call_id``. The producer here is
    the only emitter for the per-call ``log/tool_call`` row in the
    think path; ``SafeExecutor.execute`` emits it once during tool
    execution and the node never duplicates.
    """
    tool_calls = list(response.tool_calls or ())
    writer.append_assistant_message(
        turn=step,
        step=step,
        role="assistant",
        content=response.text,
        tool_calls=[
            {
                "id": tc.call_id,
                "name": tc.name,
                "arguments": tc.arguments,
            }
            for tc in tool_calls
        ]
        or None,
        usage=response.usage,
    )
    for tc in tool_calls:
        writer.append_tool_call(
            turn=step,
            step=step,
            call_id=tc.call_id,
            name=tc.name,
            arguments=str(tc.arguments),
        )


def _resolve_port(name: str, *, input: NodeInput) -> Any:
    """Read a typed port from ``input.port_values``."""
    value = input.port_values.get(name)
    if value is None:
        raise TypeError(f"llm.persist: '{name}' port must be supplied via input.port_values")
    return value


def _resolve_state(*, context: NodeContext) -> Any:
    """Pull ``state`` from the whitelisted kernel runtime carrier."""
    runtime = getattr(context, "runtime", None)
    state_obj = getattr(runtime, "state", None) if runtime is not None else None
    if state_obj is None and runtime is not None and hasattr(runtime, "get"):
        state_obj = runtime.get("state")
    if state_obj is None:
        raise TypeError("llm.persist: 'state' must be supplied via context.runtime")
    return state_obj


def _resolve_writer(*, context: NodeContext) -> RunSessionWriterProtocol:
    """Pull the ``RunSessionWriterProtocol`` from the runtime carrier."""
    runtime = getattr(context, "runtime", None)
    writer = getattr(runtime, "writer", None) if runtime is not None else None
    if writer is None and runtime is not None and hasattr(runtime, "get"):
        writer = runtime.get("writer")
    if writer is None:
        raise TypeError("llm.persist: 'writer' must be supplied via context.runtime")
    return writer  # type: ignore[no-any-return]


@plugin(
    id="phase.think.llm.persist",
    Config=None,
    provides=("think::llm.persist",),
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
                "phase_think_llm_persist.checked",
                "phase_think_llm_persist.served",
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
    """Composite-key 注册: ``{region}::{semantic_name}``。"""
    del config
    executor = LlmPersistExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["LlmPersistExecutor", "setup"]
