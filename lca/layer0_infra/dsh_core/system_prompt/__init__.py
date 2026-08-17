"""1:1 port of ``@deepseek-ai/dsh-system-prompt``.

Registry for ordered system sections, dynamic context, tool schemas, and
prompt variables.
"""

from __future__ import annotations

import copy
import functools
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from lca.layer0_infra.dsh_core.scope import ScopeKey
from lca.layer0_infra.dsh_core.scope.store import (
    AnonymousEntries,
    NamedEntries,
    ScopedLayers,
    ScopeLayer,
)
from lca.layer0_infra.plugin.kernel._context import PluginContext
from lca.layer0_infra.plugin.kernel._service import Service

# ---------------------------------------------------------------------------
# Types from ``@deepseek-ai/dsh-llm`` (full port pending)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolSchema:
    """One tool's model-facing schema (``@deepseek-ai/dsh-llm``)."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ContextSnapshotSection:
    """One named contribution to a snapshot-form context (``@deepseek-ai/dsh-llm``)."""

    name: str
    text: str


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssembleContext:
    """Merge-extensible context for one prompt assembly."""

    scope: ScopeKey | None = None
    signal: Any = None  # asyncio-compatible abort signal


@dataclass(frozen=True)
class PromptSection:
    """One contributed section of the system prompt (registry input)."""

    name: str
    order: int
    text: str | Callable[[AssembleContext], str]
    complete: bool = False


@dataclass(frozen=True)
class PromptContext:
    """Dynamic model context materialized as a durable user-role snapshot."""

    name: str
    order: int
    text: str | Callable[[AssembleContext], str]


@dataclass
class AssembledSection:
    """One section of an assembly: :class:`PromptSection` with text resolved."""

    name: str
    text: str


@dataclass
class AssembledContext:
    """One resolved dynamic context contribution."""

    name: str
    text: str


@dataclass(frozen=True)
class ToolProviderResult:
    """Tool schemas visible in one assembly and their pre-restriction name set."""

    schemas: tuple[ToolSchema, ...]
    known_names: tuple[str, ...] | None = None


@dataclass
class PromptAssembly:
    """Merge-extensible assembled model input.

    Sections and contexts remain uninterpolated until rendered; tools are
    already in canonical order.
    """

    sections: list[AssembledSection]
    contexts: list[AssembledContext]
    tools: list[ToolSchema]
    variables: dict[str, str | None]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PERSONA_SECTION: str = "deployment:persona"
"""The deployment persona's section name."""

PERSONA_ORDER: int = 0
"""Prompt order of the persona slot; the first section a model reads."""

TOOL_ORDER_REST: str = "<unlisted-tool>"
"""Reserved :attr:`Config.tool_order` marker for unlisted tools."""

_VARIABLE_NAME: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*$")
"""Valid variable names: how they are written between the braces."""

_GROUP_AT: re.Pattern[str] = re.compile(r"^\{\{([^{}]*)\}\}")
"""A complete ``{{...}}`` reference group at the scan position (validated after)."""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Plugin config: the deployment-authored fragment of the system prompt."""

    include_harness_identity: bool = True
    include_runtime_context: bool = True
    persona: str = ""
    tool_order: list[str] | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

ToolProvider = Callable[[AssembleContext], ToolProviderResult]
"""One tool-schema provider stored in a prompt layer."""

VariableProvider = Callable[[AssembleContext], str | None]
"""One prompt-variable provider stored in a prompt layer."""


def _validate_tool_order(tool_order: list[str] | None) -> list[str] | None:
    """Validate duplicate names and the required :data:`TOOL_ORDER_REST` marker."""
    if tool_order is None:
        return None
    seen: set[str] = set()
    for name in tool_order:
        if name in seen:
            raise ValueError(f'toolOrder lists "{name}" more than once')
        seen.add(name)
    if TOOL_ORDER_REST not in seen:
        raise ValueError(
            f'toolOrder must contain the "{TOOL_ORDER_REST}" rest entry '
            "(where unlisted tools are inserted)"
        )
    return tool_order


def _compare_tool_names(a: ToolSchema, b: ToolSchema) -> int:
    """Lexicographic (code-unit) name comparison — locale-independent."""
    if a.name < b.name:
        return -1
    if a.name > b.name:
        return 1
    return 0


def order_tools(
    tools: list[ToolSchema],
    tool_order: list[str] | None,
    known_names: set[str],
) -> list[ToolSchema]:
    """Apply configured tool order, inserting unlisted tools lexicographically.

    Unknown configured names fail; known but restricted names may be absent.
    """
    reserved = next((t for t in tools if t.name == TOOL_ORDER_REST), None)
    if reserved is not None:
        raise ValueError(
            f'tool provider returned reserved tool name "{TOOL_ORDER_REST}" '
            "(reserved for toolOrder's rest entry)"
        )
    if tool_order is None:
        return sorted(tools, key=functools.cmp_to_key(_compare_tool_names))
    unknown = [n for n in tool_order if n != TOOL_ORDER_REST and n not in known_names]
    if unknown:
        suffix = "s" if len(unknown) > 1 else ""
        known_list = ", ".join(sorted(known_names)) or "(none)"
        names_str = ", ".join(f'"{n}"' for n in unknown)
        raise ValueError(
            f"toolOrder lists unregistered tool{suffix} {names_str}; known tools: {known_list}"
        )
    listed = set(tool_order)
    rest = sorted(
        [t for t in tools if t.name not in listed],
        key=functools.cmp_to_key(_compare_tool_names),
    )

    result: list[ToolSchema] = []
    for name in tool_order:
        if name == TOOL_ORDER_REST:
            result.extend(rest)
        else:
            result.extend(t for t in tools if t.name == name)
    return result


def _interpolate(
    input_: AssembledSection | AssembledContext,
    variables: dict[str, str | None],
    kind: str,
) -> str:
    """Interpolate one section or context and attribute diagnostics to its owning input.

    Interpolates strict ``{{variable}}`` references.  Malformed, unknown, or
    undefined references raise; a lone ``{{`` without any later ``}}`` is
    literal prose, and substituted values are not scanned again.
    """
    text = input_.text
    result: list[str] = []
    last = 0
    open_idx = text.find("{{")
    while open_idx >= 0:
        group = _GROUP_AT.search(text, open_idx)
        if group is None or group.start() != open_idx:
            # A later closing brace makes this malformed; otherwise literal prose.
            if text.find("}}", open_idx + 2) >= 0:
                snippet = text[open_idx : open_idx + 16]
                raise ValueError(
                    f'malformed prompt variable reference at "{snippet}…" '
                    f'in {kind} "{input_.name}" '
                    "(references are complete simple {{name}} groups)"
                )
            result.append(text[last : open_idx + 2])
            last = open_idx + 2
            open_idx = text.find("{{", last)
            continue
        # ``{{}}`` yields an empty name and follows the malformed-reference path.
        name = group.group(1)
        if not _VARIABLE_NAME.match(name):
            raise ValueError(
                f'malformed prompt variable reference "{{{{{name}}}}}" '
                f'in {kind} "{input_.name}" '
                f"(variable names match {_VARIABLE_NAME.pattern})"
            )
        if name not in variables:
            known = list(variables.keys())
            known_str = ", ".join(known) if known else "(none)"
            raise ValueError(
                f'unknown prompt variable "{{{{{name}}}}}" '
                f'in {kind} "{input_.name}"; '
                f"registered variables: {known_str}"
            )
        value = variables[name]
        if value is None:
            raise ValueError(
                f'prompt variable "{{{{{name}}}}}" has no value for this assembly '
                f'({kind} "{input_.name}")'
            )
        result.append(text[last:open_idx])
        result.append(value)
        last = open_idx + group.end()
        open_idx = text.find("{{", last)
    result.append(text[last:])
    return "".join(result)


# ---------------------------------------------------------------------------
# Public render functions
# ---------------------------------------------------------------------------


def render_prompt(assembly: PromptAssembly) -> str:
    """Interpolate strict ``{{variable}}`` references, drop empty sections, join.

    Malformed, unknown, or undefined references raise; a lone ``{{`` without
    any later ``}}`` is literal prose, and substituted values are not scanned
    again.

    Returns:
        The rendered prompt, or ``''`` when all sections are empty.
    """
    parts: list[str] = []
    for section in assembly.sections:
        text = _interpolate(section, assembly.variables, "section")
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def render_context_snapshot(assembly: PromptAssembly) -> str:
    """Render the complete dynamic context snapshot."""
    return join_context_sections(render_context_sections(assembly))


def join_context_sections(
    sections: list[ContextSnapshotSection] | tuple[ContextSnapshotSection, ...],
) -> str:
    """The model-facing snapshot text for an already-rendered section list.

    Returns:
        The current full snapshot, or ``''`` when no context is active.
    """
    body = "\n\n".join(s.text for s in sections)
    if not body:
        return ""
    return (
        "Current runtime context. This snapshot supersedes earlier "
        f"runtime-context snapshots.\n\n{body}"
    )


def render_context_sections(assembly: PromptAssembly) -> list[ContextSnapshotSection]:
    """The same snapshot, kept as the named contributions it was assembled from.

    Returns:
        One entry per contributing context that rendered to non-empty text.
    """
    result: list[ContextSnapshotSection] = []
    for context in assembly.contexts:
        text = _interpolate(context, assembly.variables, "context")
        if text:
            result.append(ContextSnapshotSection(name=context.name, text=text))
    return result


# ---------------------------------------------------------------------------
# PromptLayer
# ---------------------------------------------------------------------------


class PromptLayer(ScopeLayer):
    """All prompt registrations owned by one global or scoped layer."""

    def __init__(self, scope: ScopeKey | None) -> None:
        self.sections: NamedEntries[PromptSection] = NamedEntries(
            lambda name: ValueError(
                f'prompt section "{name}" is already registered'
                + (
                    " (for a per-agent override, register through that agent's `agent.ctx` instead)"
                    if scope is None
                    else " in this scope"
                )
            )
        )
        self.contexts: NamedEntries[PromptContext] = NamedEntries(
            lambda name: ValueError(
                f'prompt context "{name}" is already registered'
                + (
                    " (for a per-agent override, register through that agent's `agent.ctx` instead)"
                    if scope is None
                    else " in this scope"
                )
            )
        )
        self.runtime_context_suppressors: AnonymousEntries[bool] = AnonymousEntries()
        self.tool_providers: AnonymousEntries[ToolProvider] = AnonymousEntries()
        self.variables: NamedEntries[VariableProvider] = NamedEntries(
            lambda name: ValueError(
                f'prompt variable "{name}" is already registered'
                + (
                    " (for a per-agent value, register through that agent's `agent.ctx` instead)"
                    if scope is None
                    else " in this scope"
                )
            )
        )

    def is_empty(self) -> bool:
        """Whether this layer owns no prompt registrations."""
        return (
            self.sections.is_empty()
            and self.contexts.is_empty()
            and self.runtime_context_suppressors.is_empty()
            and self.tool_providers.is_empty()
            and self.variables.is_empty()
        )


# ---------------------------------------------------------------------------
# SystemPrompt service
# ---------------------------------------------------------------------------


class SystemPrompt(Service):
    """Registry service for the prompt inputs assembled before each model step."""

    name: ClassVar[str] = "systemPrompt"

    def __init__(self, ctx: PluginContext, config: Config | None = None) -> None:
        cfg = config or Config()

        import asyncio

        def _on_change() -> None:
            try:
                loop = asyncio.get_running_loop()
                task = loop.create_task(ctx.emit("system-prompt/change"))
                task.add_done_callback(lambda _: None)  # prevent GC warning
            except RuntimeError:
                pass

        self._layers: ScopedLayers[PromptLayer] = ScopedLayers(
            lambda scope: PromptLayer(scope),
            _on_change,
        )
        self._tool_order: list[str] | None = _validate_tool_order(cfg.tool_order)

        super().__init__(ctx, cfg)

        # Keep harness-owned openers independent of the selected loop plugin.
        if cfg.include_harness_identity:
            self.section(
                PromptSection(
                    name="harness:identity",
                    order=-100,
                    text="You are an AI agent powered by DeepSeek Harness.",
                )
            )
        self.section(
            PromptSection(
                name=PERSONA_SECTION,
                order=PERSONA_ORDER,
                text=cfg.persona,
            )
        )
        if not cfg.include_runtime_context:
            self.suppress_runtime_context()

    # -- Registration API ----------------------------------------------------

    def section(self, section: PromptSection) -> Callable[[], None]:
        """Register an ordered prompt section in the calling context's scope.

        A scoped section shadows a global section with the same name;
        duplicates within one layer and non-finite orders raise.
        Registration and disposal emit ``system-prompt/change``.

        Returns:
            The exact Cordis effect disposer.
        """
        if not isinstance(section.order, (int, float)) or not (
            -float("inf") < section.order < float("inf")
        ):
            raise TypeError(f'prompt section "{section.name}" order must be a finite number')
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.sections.insert(section.name, section),
            label="systemPrompt.section()",
        )

    def context(self, context: PromptContext) -> Callable[[], None]:
        """Register ordered dynamic context in the calling context's scope.

        Scoped entries shadow global entries with the same name.

        Returns:
            The exact Cordis effect disposer.
        """
        if not isinstance(context.order, (int, float)) or not (
            -float("inf") < context.order < float("inf")
        ):
            raise TypeError(f'prompt context "{context.name}" order must be a finite number')
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.contexts.insert(context.name, context),
            label="systemPrompt.context()",
        )

    def suppress_runtime_context(self) -> Callable[[], None]:
        """Suppress every dynamic runtime-context contribution in the calling scope.

        Multiple suppressors remain independently disposable.

        Returns:
            The exact Cordis effect disposer.
        """
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.runtime_context_suppressors.append(True),
            label="systemPrompt.suppressRuntimeContext()",
        )

    def tools(
        self, provider: Callable[[AssembleContext], ToolProviderResult]
    ) -> Callable[[], None]:
        """Register a tool-schema provider in the calling context's scope.

        Global and matching scoped providers both contribute; returning the
        reserved :data:`TOOL_ORDER_REST` name makes assembly fail.

        Returns:
            The exact Cordis effect disposer.
        """
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.tool_providers.append(provider),
            label="systemPrompt.tools()",
        )

    def variable(
        self,
        name: str,
        provider: Callable[[AssembleContext], str | None],
    ) -> Callable[[], None]:
        """Register a prompt variable in the calling context's scope.

        Scoped values shadow globals; invalid or duplicate names raise.
        A provider may return ``None``, but rendering a section that references
        that value then fails.

        Returns:
            The exact Cordis effect disposer.
        """
        if not _VARIABLE_NAME.match(name):
            raise ValueError(
                f'invalid prompt variable name "{name}" (must match {_VARIABLE_NAME.pattern})'
            )
        return self._layers.effect(
            self.ctx,
            lambda layer: layer.variables.insert(name, provider),
            label="systemPrompt.variable()",
        )

    # -- Assembly ------------------------------------------------------------

    async def assemble(self, context: AssembleContext | None = None) -> PromptAssembly:
        """Assemble global and scoped providers, apply canonical ordering, then
        run the assembly waterfall.

        Scoped sections and variables shadow globals.  The returned waterfall
        value is authoritative except that an effective complete section is
        restored afterwards as the sole prompt section.

        Returns:
            The post-waterfall assembly with any complete prompt enforced.
        """
        if context is None:
            context = AssembleContext()
        scope = context.scope
        scope_layers = self._layers.chain_layers(scope)
        runtime_context_suppressed = (
            not self._layers.global_layer.runtime_context_suppressors.is_empty()
            or any(not layer.runtime_context_suppressors.is_empty() for layer in scope_layers)
        )

        # Scoped variables shadow globals.
        variables: dict[str, str | None] = {}
        for name, provider in self._layers.global_layer.variables.entries():
            variables[name] = provider(context)
        # Scope-chain variables, farthest first, so the nearest scope wins.
        for layer in scope_layers:
            for name, provider in layer.variables.entries():
                variables[name] = provider(context)

        # Scoped sections shadow globals before the stable order sort.
        section_by_name = self._layers.merge(scope, lambda layer: layer.sections)
        context_by_name = self._layers.merge(scope, lambda layer: layer.contexts)

        # Validate order against pre-restriction names while collecting schemas.
        tool_providers: list[ToolProvider] = list(self._layers.global_layer.tool_providers.values())
        for layer in scope_layers:
            tool_providers.extend(layer.tool_providers.values())

        collected: list[ToolSchema] = []
        known_names: set[str] = set()
        for provider_fn in tool_providers:
            result = provider_fn(context)
            schemas = [
                ToolSchema(
                    name=s.name,
                    description=s.description,
                    parameters=copy.deepcopy(s.parameters),
                )
                for s in result.schemas
            ]
            accepted_known = (
                result.known_names
                if result.known_names is not None
                else tuple(s.name for s in schemas)
            )
            collected.extend(schemas)
            for n in accepted_known:
                known_names.add(n)

        section_definitions = sorted(section_by_name.values(), key=lambda s: s.order)
        complete_sections = [s for s in section_definitions if s.complete]
        if len(complete_sections) > 1:
            names = ", ".join(f'"{s.name}"' for s in complete_sections)
            raise ValueError(f"multiple complete prompt sections are active: {names}")

        complete_section: AssembledSection | None = None
        sections: list[AssembledSection] = []
        for section_def in section_definitions:
            text = section_def.text(context) if callable(section_def.text) else section_def.text
            assembled = AssembledSection(name=section_def.name, text=text)
            if section_def.complete:
                complete_section = AssembledSection(name=assembled.name, text=assembled.text)
            sections.append(assembled)

        contexts_list: list[AssembledContext] = []
        if not runtime_context_suppressed:
            sorted_contexts = sorted(context_by_name.values(), key=lambda c: c.order)
            for entry in sorted_contexts:
                text = entry.text(context) if callable(entry.text) else entry.text
                contexts_list.append(AssembledContext(name=entry.name, text=text))

        assembly = PromptAssembly(
            sections=sections,
            contexts=contexts_list,
            tools=order_tools(collected, self._tool_order, known_names),
            variables=variables,
        )

        transformed: PromptAssembly = await self.ctx.waterfall(
            "system-prompt/assemble",
            assembly,
            context,
            terminal=lambda: assembly,
        )

        if complete_section is None and not runtime_context_suppressed:
            return transformed
        return PromptAssembly(
            sections=([complete_section] if complete_section is not None else transformed.sections),
            contexts=[] if runtime_context_suppressed else transformed.contexts,
            tools=transformed.tools,
            variables=transformed.variables,
        )
