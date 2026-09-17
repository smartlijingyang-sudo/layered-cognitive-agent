"""``think.history.assemble`` graph node (spec §D + §G).

Single responsibility: derive the :class:`ModelVisibleRequest` from
:class:`RunSessionWriter` by orphan-dropping dangling tool/result messages,
and source the system prompt per spec §G so the LLM has identity / rules.

Mirrors OpenAI Agents SDK's ``drop_orphan_function_calls`` pattern at every
LLM-call preparation step. The orphan-drop lives on
:meth:`RunSessionWriter.derive_messages`; this node is the typed-boundary
adapter that wires the writer into the think subgraph's LLM dispatch port.

System prompt seam (spec §G — fix duplication + ensure LLM has identity):

The folded ``EpochHeader.system`` only becomes non-empty when
``ModelVisibleHook.capture_pre_llm`` runs *inside* the LLM adapter — too
late for history.assemble, which prepares the request before
``think.llm.invoke``. Two-tier fallback at this seam:

  1. folded header (``writer.request_header().system``) — replay-safe
  2. live render (``turn_render.trace.system_prompt_text`` from
     ``think.reason.render`` one node earlier)

The prior third tier (``role_profile`` composition) is removed: the
role identity lives on the Brain (``brain.role_profile``, consumed by
``think.reason.render``), so this node no longer falls back to a
runtime-cached profile. If both header and render are empty the LLM
is dispatched without an explicit system prompt — the same behavior
the live render path produces when ``system_prompt_text`` is empty.

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
from lca.contracts.models.cognition.boundary import ForkedTools
from lca.contracts.protocols import Tool
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


def _tool_to_spec(tool: Tool) -> dict[str, Any]:
    """Serialize one Tool Protocol instance to OpenAI function-calling tool spec.

    Mirrors ``lca.infrastructure.llm_adapter.openai_compat.chat._chat_completions.to_openai_chat_tool_spec``
    — kept local to avoid an infrastructure → cognition import (lca/nodes/
    lives in L2 cognition per ADR-0220). The chat-completions adapter
    detects the dict shape at the wire boundary (see PR-3.8.borrow-tools-wire)
    so passing the wire-ready dict here is safe.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _forked_to_tools(forked: object) -> tuple[dict[str, Any], ...]:
    """Project ``ForkedTools.items`` into wire-ready tool specs.

    Tolerates a missing or non-ForkedTools port: returns ``()`` so the
    LLM call still works for runs without tools (tests, no-tool agents).
    """
    if not isinstance(forked, ForkedTools) or not forked.items:
        return ()
    return tuple(_tool_to_spec(tool) for tool in forked.items)


@dataclass(frozen=True, slots=True)
class HistoryDeriveExecutor:
    """think.history.assemble 节点:writer + response + forked_tools → :class:`ModelVisibleRequest`.

    Spec §E: history.assemble projects the LLM-visible slice (messages +
    system + tools) from the typed-boundary inputs. ``tools`` comes from
    the upstream ``ForkedTools`` port (ADR-0220 §4 boundary DTO); the
    writer owns the message stream, not the tool schema source.

    Spec §G: ``system`` is sourced via a two-tier fallback
    (folded header → live render from ``turn_render.trace``). The fallback
    exists because the folded header publishes during the LLM call
    itself (too late for this node); see module docstring for details.
    """

    semantic_name: str = "history.derive"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = (
        "state",
        "writer",
        "forked_tools",
        "turn_render",
    )
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
        system = _resolve_system(
            header=header,
            render=input.port_values.get("turn_render"),
        )
        tools = _forked_to_tools(input.port_values.get("forked_tools"))
        return NodeOutput(
            port_values={
                "model_visible_request": ModelVisibleRequest(
                    messages=messages, system=system, tools=tools
                )
            }
        )


def _resolve_port(name: str, *, input: NodeInput, context: NodeContext) -> Any:
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


def _system_from_render(render: Any) -> str:
    """Pull the rendered system prompt from the upstream ``turn_render`` port.

    ``think.reason.render`` runs one step earlier in the subgraph and
    emits a typed-boundary :class:`ReasonerTurnRender` whose ``trace``
    carries the joined ``system_prompt_text``. This is the authoritative
    per-turn render — spec §G mandates the LLM see the assembled prompt
    as ``role=system``, never as ``role=user`` and never omitted.
    """
    trace = getattr(render, "trace", None)
    if trace is None:
        return ""
    text = getattr(trace, "system_prompt_text", None)
    return text if isinstance(text, str) else ""


def _resolve_system(
    *,
    header: Any,
    render: Any,
) -> str:
    """Pick the system prompt using spec §G's two-tier fallback.

    Priority (highest wins):

    1. ``writer.request_header().system`` — folded journal state.
       Replay-safe path: a run reconstructed from ``spine.jsonl`` keeps
       the historical header even when the live render emits newer text.
    2. ``turn_render.trace.system_prompt_text`` — the live per-turn render
       produced by ``think.reason.render`` one node earlier. Needed because
       ``spine.llm.request.header`` is published *inside* the LLM adapter
       call, after this node prepares the request, so the folded header is
       always one turn behind (or absent on the first turn).

    Header None / empty / non-string is treated as "no header" so the
    fallback chain runs even when fold produced a header object with
    no system field (canonical normalization drops absent strings).

    ``brain.role_profile`` is the sole authority for role identity —
    consumed by ``think.reason.render`` and reflected via
    ``turn_render.trace.system_prompt_text``; this node does not compose a
    prompt of its own.
    """
    from_header = _system_from_header(header)
    if from_header:
        return from_header
    return _system_from_render(render)


@plugin(
    id="phase.think.history.derive",
    Config=None,
    provides=("think::history.derive",),
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
