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

import re
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
from lca.infrastructure.memory.contextfiles.adapters.disk import DiskFileStore
from lca.infrastructure.memory.contextfiles.adapters.polling import (
    ensure_standing_watcher,
    poll_standing_home,
)
from lca.infrastructure.memory.contextfiles.domain.layout import layout_for_home
from lca.infrastructure.memory.contextfiles.service.alignment import load_alignment_synthesis
from lca.infrastructure.memory.contextfiles.service.assembly import (
    refresh_standing_backstory,
)
from lca.infrastructure.memory.contextfiles.service.compaction import (
    preserve_standing_sections,
)
from lca.nodes._resolve import resolve_typed_port_or_runtime


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


def _forked_to_tools_deferred(
    forked: object,
) -> tuple[tuple[dict[str, Any], ...], str]:
    """Defer-aware projection → ``(wire specs, catalog text)``.

    No ambient defer session (tests, legacy run entries) → legacy full
    projection and no catalog, so behavior is unchanged.
    """
    from lca.infrastructure.tool_defer.session import current_defer_session

    session = current_defer_session()
    if session is None:
        return _forked_to_tools(forked), ""
    if not isinstance(forked, ForkedTools):
        return (), ""
    return session.render_turn()


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

    ADR-0248: gated 模式的声带契约与 Reply-First 提醒由注册的
    ``vocal_contract`` prompt section 在 ``think.reason.render`` 渲染时注入，
    本节点不自行拼接提示词内容。
    """

    semantic_name: str = "memory.derive"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = (
        PortName("state"),
        PortName("writer"),
        PortName("forked_tools"),
        PortName("turn_render"),
    )
    declared_outputs: tuple[PortName, ...] = (PortName("model_visible_request"),)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Resolve declared ports, build the request, return typed output."""
        state = resolve_typed_port_or_runtime(PortName("state"), input=input, context=context, node="memory.derive")
        writer = resolve_typed_port_or_runtime(PortName("writer"), input=input, context=context, node="memory.derive")
        del state
        messages = writer.derive_messages()
        header = writer.request_header()
        system = _resolve_system(
            header=header,
            render=input.port_values.get(PortName("turn_render")),
        )
        system = _refresh_standing(system, runtime=context.runtime)
        system = _append_standing_diff(system, runtime=context.runtime)
        system = _append_alignment_synthesis(system, runtime=context.runtime)
        tools, defer_catalog = _forked_to_tools_deferred(input.port_values.get(PortName("forked_tools")))
        # The folded header is last turn's request, catalog included.
        # Appending again stacks a second copy of the same directory.
        system = _strip_defer_catalog(system)
        if defer_catalog:
            system = f"{system}\n\n{defer_catalog}" if system else defer_catalog
        return NodeOutput(
            port_values={
                PortName("model_visible_request"): ModelVisibleRequest(
                    messages=messages, system=system, tools=tools
                )
            }
        )


_DEFER_CATALOG_HEADER = "Deferred tool namespaces (not yet loaded):"
_DEFER_CATALOG_PATTERN = re.compile(
    r"\n*" + re.escape(_DEFER_CATALOG_HEADER) + r"(?:\n[^\n]+)*\n*",
)
_DEFER_SENTINEL_PATTERN = re.compile(
    r"\n*<!-- BEGIN DEFERRED TOOL CATALOG -->.*?<!-- END DEFERRED TOOL CATALOG -->\n*",
    re.DOTALL,
)


def _strip_defer_catalog(system: str) -> str:
    """Drop every previously appended defer catalog, leaving the prompt.

    Uses paragraph-level boundary matching to strip catalog blocks without
    coupling to internal DeferPolicy discovery rules. Supports both explicit
    sentinel markers and canonical header blocks.
    """
    if not system:
        return ""
    if "<!-- BEGIN DEFERRED TOOL CATALOG -->" in system:
        system = _DEFER_SENTINEL_PATTERN.sub("\n\n", system)
    if _DEFER_CATALOG_HEADER in system:
        system = _DEFER_CATALOG_PATTERN.sub("\n\n", system)
    return system.strip()


def _append_standing_diff(system: str, *, runtime: object) -> str:
    """Append a unified diff when standing files changed since the last poll.

    The first poll for a home only records the baseline. The cursor lives in
    the process, so this node does not write agent state or the home. A live
    run (one with per-turn capability bindings) starts the real-time watcher
    so diffs are captured at detection time, not lazily at assembly.
    """

    home_path = _home_path(runtime)
    if not home_path:
        return system
    if _live_bindings_home() == home_path:
        ensure_standing_watcher(home_path)
    note = poll_standing_home(home_path)
    if not note:
        return system
    if not system:
        return note
    return f"{system}\n\n{note}"


def _append_alignment_synthesis(system: str, *, runtime: object) -> str:
    """Append the nightly alignment synthesis when the home has one.

    The synthesis is a soft alignment signal. It is read from disk on every
    assembly so a fresh dream pass reaches the model without a restart.
    When the standing snapshot already injected the synthesis file, it is
    already visible and must not be appended a second time.
    """

    home_path = _home_path(runtime)
    if not home_path:
        return system
    if "INJECTED FILE: dreams/alignment/derived/ALIGNMENT_SYNTHESIS.md" in system:
        return system
    try:
        synthesis = load_alignment_synthesis(
            DiskFileStore(home_path),
            layout=layout_for_home(home_path),
        )
    except OSError:
        return system
    if not synthesis.strip():
        return system
    if not system:
        return synthesis
    return f"{system}\n\n{synthesis}"


def _live_bindings_home() -> str | None:
    """Return the home path from the per-turn capability bindings, if any."""

    try:
        from lca.infrastructure.runtime_plane.capability_bindings import (
            current_bindings_view,
        )

        bindings = current_bindings_view()
    except Exception:
        return None
    bound = getattr(bindings, "home_path", None) if bindings is not None else None
    return str(bound) if bound else None


def _refresh_standing(system: str, *, runtime: object) -> str:
    """Replace injected standing blocks from disk when a home is bound.

    A home-bound run, including a derived subagent, always receives the
    standing snapshot. When the upstream prompt already has injection
    markers, those blocks are rewritten from disk. When it has none, the
    snapshot is appended so a child that lost the parent's markers still
    sees the five files.
    """

    home_path = _home_path(runtime)
    if not home_path:
        return system
    if "<!-- INJECTED FILE:" not in system:
        snapshot = refresh_standing_backstory(home_path, "")
        if not snapshot:
            return system
        if not system:
            return snapshot
        return f"{system}\n\n{snapshot}"
    return preserve_standing_sections(
        system,
        DiskFileStore(home_path),
        layout=layout_for_home(home_path),
    )


def _home_path(runtime: object) -> str | None:
    home = getattr(runtime, "home_path", None)
    if not home:
        get = getattr(runtime, "get", None)
        if callable(get):
            home = get("home_path")
    if home:
        return str(home)
    return _live_bindings_home()


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
    provides=("think::memory.derive",),
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
