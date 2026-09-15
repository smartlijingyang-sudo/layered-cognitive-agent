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
``think.llm.dispatch``. Three-tier fallback at this seam:

  1. folded header (``writer.request_header().system``) — replay-safe
  2. live render (``response.trace.system_prompt_text`` from
     ``think.reason.render`` one node earlier) — fixes the
     ``system=""`` regression (run_a0cdcd40d8b9)
  3. ``role_profile`` composition — last-resort for legacy runtimes

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

    Spec §G: ``system`` is sourced via a three-tier fallback
    (folded header → live render from ``response.trace`` →
    ``role_profile`` composition). The fallback exists because the
    folded header publishes during the LLM call itself (too late for
    this node); see module docstring for details.
    """

    semantic_name: str = "history.derive"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = (
        "state",
        "writer",
        "forked_tools",
        "response",
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
            response=input.port_values.get("response"),
            runtime=getattr(context, "runtime", None),
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


def _system_from_response(response: Any) -> str:
    """Pull the rendered system prompt from an upstream ``ReasonerTurnRender``.

    ``think.reason.render`` runs one step earlier in the subgraph and
    emits a typed-boundary :class:`ReasonerTurnRender` whose ``trace``
    carries the joined ``system_prompt_text``. This is the authoritative
    per-turn render — spec §G mandates the LLM see the assembled prompt
    as ``role=system``, never as ``role=user`` and never omitted.
    """
    trace = getattr(response, "trace", None)
    if trace is None:
        return ""
    text = getattr(trace, "system_prompt_text", None)
    return text if isinstance(text, str) else ""


def _system_from_role_profile(runtime: Any) -> str:
    """Compose a minimal system prompt from a :class:`RoleProfile` on the runtime.

    Last-resort fallback when neither the folded header nor the upstream
    render are available. The Reasoner sections normally assemble richer
    text; this fallback just stitches the role's identity + goal so the
    LLM has at least an identity in legacy / minimal-render runs.

    Looks up the profile via either the canonical capability key
    ``reasoner.role_profile`` (declared in :data:`lca.contracts.capabilities
    .REASONER_ROLE_PROFILE`) or a plain ``role_profile`` attribute on the
    runtime namespace — the latter covers tests that bypass the
    capability registry.
    """
    if runtime is None:
        return ""
    getter = getattr(runtime, "get", None)
    profile: Any = None
    if callable(getter):
        profile = getter("reasoner.role_profile")
        if profile is None:
            profile = getter("role_profile")
    if profile is None:
        profile = getattr(runtime, "reasoner", None)
        if profile is not None:
            profile = getattr(profile, "role_profile", None)
    if profile is None:
        profile = getattr(runtime, "role_profile", None)
    if profile is None:
        return ""
    parts: list[str] = []
    role = getattr(profile, "role", None)
    if isinstance(role, str) and role.strip():
        parts.append(f"你是{role}.")
    goal = getattr(profile, "goal", None)
    if isinstance(goal, str) and goal.strip():
        parts.append(f"目标:{goal}")
    backstory = getattr(profile, "backstory", None)
    if isinstance(backstory, str) and backstory.strip():
        parts.append(backstory)
    return " ".join(parts)


def _resolve_system(
    *,
    header: Any,
    response: Any,
    runtime: Any,
) -> str:
    """Pick the system prompt using spec §G's three-tier fallback.

    Priority (highest wins):

    1. ``writer.request_header().system`` — folded journal state.
       Replay-safe path: a run reconstructed from ``spine.jsonl`` keeps
       the historical header even when the live render emits newer text.
    2. ``response.trace.system_prompt_text`` — the live per-turn render
       produced by ``think.reason.render`` one node earlier. Fixes
       run_a0cdcd40d8b9 where ``writer.request_header()`` was ``None``
       because ``spine.llm.request.header`` had not yet been published
       (the publish happens *inside* the LLM adapter call, after
       history.assemble prepares the request).
    3. ``role_profile``-derived composition — last resort for legacy
       runtimes / tests that do not pass a render. The rendered
       section-joined text is the authoritative system prompt; this
       fallback only ensures the LLM has at least an identity when
       the render seam is absent.

    Header None / empty / non-string is treated as "no header" so the
    fallback chain runs even when fold produced a header object with
    no system field (canonical normalization drops absent strings).
    """
    from_header = _system_from_header(header)
    if from_header:
        return from_header
    from_response = _system_from_response(response)
    if from_response:
        return from_response
    return _system_from_role_profile(runtime)


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
