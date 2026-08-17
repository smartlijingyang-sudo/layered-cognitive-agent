"""System-prompt plugin — composable prompt assembly.

Replaces monolithic ``.md`` templates with a section / context / variable
registry, aligned with DSH's ``@deepseek-ai/dsh-system-prompt`` design.

Spec reference: composable-prompt-assembly design doc.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.harness.plugin import PluginKind, PluginManifest

# ── Manifest ──────────────────────────────────────────────────────────

manifest = PluginManifest(
    id="lca.system_prompt.service",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("system_prompt",),
)

name = "lca.system_prompt.service"
provides = "system_prompt"


# ── Data types ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PromptSection:
    """An ordered section of the final system prompt."""

    name: str
    order: int
    text: str | Callable[[AssembleContext], str]


@dataclass(frozen=True)
class PromptContext:
    """A dynamic context block injected into the system prompt."""

    name: str
    order: int
    text: str | Callable[[AssembleContext], str]


@dataclass
class AssembleContext:
    """Per-assembly context — callers put whatever they need into ``values``."""

    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromptAssembly:
    """Result of ``assemble()`` — ready to be rendered into a string."""

    sections: list[PromptSection]
    contexts: list[PromptContext]
    variables: dict[str, str]


# ── Variable interpolation ───────────────────────────────────────────

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _interpolate(text: str, variables: dict[str, str]) -> str:
    """Replace ``{{name}}`` references; raise on unknown variables."""

    def _replace(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in variables:
            raise ValueError(f"Unknown prompt variable: '{{{{{key}}}}}'")
        return variables[key]

    return _VAR_RE.sub(_replace, text)


# ── Service ───────────────────────────────────────────────────────────

_Disposer = Callable[[], None]
_AssembleHook = Callable[[AssembleContext, PromptAssembly], None]


class SystemPromptService:
    """Composable prompt assembly service.

    Sections, contexts, and variables are registered dynamically.
    ``assemble()`` snapshots them into a ``PromptAssembly``;
    ``render()`` resolves callables, interpolates variables, drops
    empty sections, and joins with ``"\\n\\n"``.
    """

    def __init__(self) -> None:
        self._sections: dict[str, PromptSection] = {}
        self._contexts: dict[str, PromptContext] = {}
        self._variables: dict[str, Callable[[], str]] = {}
        self._hooks: list[_AssembleHook] = []

    # ── Registration (each returns a disposer) ──

    def section(
        self,
        name: str,
        order: int,
        text: str | Callable[[AssembleContext], str],
    ) -> _Disposer:
        """Register a prompt section. Returns a disposer that removes it."""
        self._sections[name] = PromptSection(name=name, order=order, text=text)
        return lambda: self._sections.pop(name, None)

    def context(
        self,
        name: str,
        order: int,
        text: str | Callable[[AssembleContext], str],
    ) -> _Disposer:
        """Register a dynamic context block. Returns a disposer."""
        self._contexts[name] = PromptContext(name=name, order=order, text=text)
        return lambda: self._contexts.pop(name, None)

    def variable(
        self,
        name: str,
        provider: Callable[[], str],
    ) -> _Disposer:
        """Register a variable provider. Returns a disposer."""
        self._variables[name] = provider
        return lambda: self._variables.pop(name, None)

    def on_assemble(self, hook: _AssembleHook) -> _Disposer:
        """Register a waterfall hook called during ``assemble()``.

        Hooks receive the ``AssembleContext`` and the in-flight
        ``PromptAssembly`` and may mutate it (e.g. inject sections).
        """
        self._hooks.append(hook)
        return lambda: self._hooks.remove(hook)

    # ── Assembly & rendering ──

    def assemble(self, ctx: AssembleContext | None = None) -> PromptAssembly:
        """Snapshot all registrations into a ``PromptAssembly``."""
        if ctx is None:
            ctx = AssembleContext()

        variables = {name: provider() for name, provider in self._variables.items()}
        assembly = PromptAssembly(
            sections=list(self._sections.values()),
            contexts=list(self._contexts.values()),
            variables=variables,
        )

        for hook in self._hooks:
            hook(ctx, assembly)

        return assembly

    def render(self, assembly: PromptAssembly) -> str:
        """Resolve callables, interpolate variables, drop empties, join."""
        ac = AssembleContext()  # empty — render has no extra context

        all_blocks: list[tuple[int, str]] = []

        for section in assembly.sections:
            text = section.text(ac) if callable(section.text) else section.text
            text = text.strip()
            if text:
                all_blocks.append((section.order, text))

        for context_block in assembly.contexts:
            text = context_block.text(ac) if callable(context_block.text) else context_block.text
            text = text.strip()
            if text:
                all_blocks.append((context_block.order, text))

        all_blocks.sort(key=lambda t: t[0])

        rendered = [_interpolate(text, assembly.variables) for _, text in all_blocks]
        return "\n\n".join(rendered)


# ── Plugin entry point ────────────────────────────────────────────────


def apply(ctx: Any, config: Any) -> None:
    service = SystemPromptService()
    ctx.mount("system_prompt", service)
