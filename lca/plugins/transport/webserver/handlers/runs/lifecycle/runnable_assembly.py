"""Materialize generic run inputs and delegate to one adapter resolver.

The carrier resolves the profile-selected LLM and tools, then passes one
:class:`RunnableBuildRequest` to the profile-selected mode adapter.  This
generic module contains no mode fallback policy or mode implementation
knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from lca.application.api import Agent, Team
from lca.contracts.mechanisms.capability import provider_current, require_capability
from lca.contracts.models.core.plane import PlaneBindings
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.runtime.infra import MachineResolver, Tool
from lca.contracts.protocols.session.run_mode import RunModeRegistryProtocol
from lca.infrastructure.observability import BoundObservability
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession

if TYPE_CHECKING:
    from cordis import Context


class LlmResolver(Protocol):
    """Resolve the concrete LLM implementation selected by the booted profile."""

    def resolve(self) -> LLMAdapter: ...


@dataclass(frozen=True, slots=True)
class RunnableAssemblyRequest:
    """All run-scoped inputs needed to select and prepare a mode adapter."""

    session: RunSession
    question: str
    mode: str
    observability: BoundObservability
    bindings: PlaneBindings | None
    scope: Context | None
    llm_resolver: LlmResolver
    machine_resolver: MachineResolver | None = None


@dataclass(frozen=True, slots=True)
class RunnableBuildRequest:
    """Adapter input after profile-backed dependencies are materialized."""

    assembly: RunnableAssemblyRequest
    llm: LLMAdapter
    tools: tuple[Tool, ...]


class CognitiveRunnableAssembler:
    """Materialize shared run inputs and delegate through ``run_mode_registry``.

    The existing registry protocol is the real mode-selection seam: profiles
    can replace any ``ModeAdapter`` without changing this generic assembler.
    Keeping a second resolver protocol and a registry-to-adapter wrapper here
    only duplicated that contract and obscured the selected adapter's interface.
    """

    def __init__(self, *, mode_registry: RunModeRegistryProtocol) -> None:
        self._mode_registry = mode_registry

    async def assemble(self, request: RunnableAssemblyRequest) -> Agent | Team:
        """Materialize common dependencies and delegate to the selected adapter."""

        prepared = RunnableBuildRequest(
            assembly=request,
            llm=request.llm_resolver.resolve(),
            tools=tools_from_scope(
                request.scope,
                request.bindings,
                machine_resolver=request.machine_resolver,
                assistant_id=str(getattr(request.session, "assistant_id", "") or "").strip(),
            ),
        )
        adapter = self._mode_registry.resolve(request.mode)
        return cast("Agent | Team", await adapter.build(prepared))


def tools_from_scope(
    scope: Context | None,
    bindings: PlaneBindings | None,
    *,
    machine_resolver: MachineResolver | None = None,
    assistant_id: str = "",
) -> tuple[Tool, ...]:
    """Materialize tools from the booted tools seam; missing seams fail loudly."""

    if scope is None:
        return ()
    bind = {
        "file_store": provider_current(require_capability(scope, "file_store")),
        "bindings": bindings,
        "sandbox": provider_current(require_capability(scope, "sandbox")),
        "search": require_capability(scope, "search"),
        "skill_store": provider_current(require_capability(scope, "skills")),
        "machine_resolver": machine_resolver,
        "assistant_id": assistant_id,
    }
    return tuple(require_capability(scope, "tools").materialize(bind))


__all__ = [
    "CognitiveRunnableAssembler",
    "LlmResolver",
    "RunnableAssemblyRequest",
    "RunnableBuildRequest",
    "tools_from_scope",
]
