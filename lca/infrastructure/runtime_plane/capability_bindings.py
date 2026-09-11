"""Per-turn typed ``BindingsView`` seam — RuntimePlane.current_bindings().

ADR-0220 §7.3 / §闸门 5: ``BindingsView`` is the typed per-run capability
bag that replaces the legacy ``AgentState._xxx_ref`` private attributes.
The ``RuntimePlane`` exposes a typed ContextVar ``current_bindings()``
that the runtime loop entry point populates each turn; the graph
layer (``agent.run.phase`` / ``agent.reasoning.turn`` /
``concept.tool.fork``) reads it via this seam rather than reading
``AgentState`` private attributes.

``BindingsViewBuilder`` is the typed input surface — the runtime entry
point collects each capability reference it has registered (file_store,
sandbox, skill_store, machine_resolver, search, bindings) and passes
them to ``build()``. The seam is fail-loud: a missing builder at graph
execution time is a wiring bug, not a silent fallback.

This module lives in ``lca.infrastructure.runtime_plane`` because the
runtime plane is the only layer that may construct capability bag
references (AGENTS.md capability hard constraint). It does not
import cognition or plugins, so the dependency direction stays
one-way (contracts → infrastructure).
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from lca.contracts.models.cognition.boundary import BindingsView


@dataclass(frozen=True, slots=True)
class BindingsViewBuilder:
    """Per-turn capability references collected by the runtime entry point.

    Each field is optional: ``None`` means the runtime did not register
    that capability in this turn (the corresponding factory in
    ``ToolsService.fork_for_run`` will receive ``None`` for that key).
    The bag is purely a value carrier — it does not reach into
    ``AgentState`` or perform reflection on any model instance.

    The runtime entry point constructs one of these per turn and feeds
    it to ``set_capability_bindings()`` so the graph layer can read
    the typed ``BindingsView`` without touching state.
    """

    file_store: object | None = None
    sandbox: object | None = None
    skill_store: object | None = None
    machine_resolver: object | None = None
    search: object | None = None
    bindings: object | None = None

    def build(self) -> BindingsView:
        """Project the builder onto the typed ``BindingsView`` boundary DTO.

        Construction is pure — no I/O, no env reads, no state mutation.
        Callers (typically the graph layer) receive a frozen
        ``BindingsView`` whose every field is statically known.
        """
        return BindingsView(
            file_store=self.file_store,
            sandbox=self.sandbox,
            skill_store=self.skill_store,
            machine_resolver=self.machine_resolver,
            search=self.search,
            bindings=self.bindings,
        )


_capability_bindings: ContextVar[BindingsViewBuilder | None] = ContextVar(
    "lca_runtime_capability_bindings",
    default=None,
)


def set_capability_bindings(
    builder: BindingsViewBuilder,
) -> Token[BindingsViewBuilder | None]:
    """Bind a per-turn ``BindingsViewBuilder`` to the runtime plane seam.

    Returns the reset token; the caller MUST reset it (typically via
    ``capability_bindings_scope``). Re-binding without resetting leaks
    the previous turn's bindings into the next turn — fail-loud via
    a programmer error rather than a runtime fall-through.
    """
    return _capability_bindings.set(builder)


def reset_capability_bindings(
    token: Token[BindingsViewBuilder | None],
) -> None:
    """Release the per-turn ``BindingsViewBuilder`` token."""
    _capability_bindings.reset(token)


def current_bindings() -> BindingsViewBuilder | None:
    """Return the active per-turn ``BindingsViewBuilder``, or ``None``.

    The graph layer (``agent.run.phase`` entry, ``concept.tool.fork``
    fallback) calls this when no upstream typed ``BindingsView`` has
    been wired. ``None`` means "no per-turn bindings registered" — the
    caller decides whether to fail loud or to skip.
    """
    return _capability_bindings.get()


def current_bindings_view() -> BindingsView | None:
    """Typed boundary DTO convenience: project the builder or return ``None``.

    Most graph-layer code wants the typed ``BindingsView`` directly,
    not the builder. This helper bridges the seam: callers that have
    a builder turn it into the boundary DTO in one call. The seam
    itself stays builder-shaped because the runtime layer may want
    to inspect the builder (e.g. log capability misses) before
    projecting.
    """
    builder = _capability_bindings.get()
    if builder is None:
        return None
    return builder.build()


__all__ = [
    "BindingsViewBuilder",
    "current_bindings",
    "current_bindings_view",
    "reset_capability_bindings",
    "set_capability_bindings",
]
