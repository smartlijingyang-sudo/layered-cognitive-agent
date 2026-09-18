"""Materialize generic run inputs and delegate to one adapter resolver.

The carrier resolves the profile-selected LLM and tools, then passes one
:class:`RunnableBuildRequest` to the profile-selected mode adapter.  This
generic module contains no mode fallback policy or mode implementation
knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, cast

from lca.application.api.api import Agent, Team
from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.mechanisms.capability.capability import (
    MissingCapabilityError,
    provider_current,
    require_capability,
)
from lca.contracts.models.core.state.plane import PlaneBindings
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols import LLMAdapter
from lca.contracts.protocols.runtime.infra.infra import MachineResolver, Tool
from lca.contracts.protocols.session.run.mode import RunModeRegistryProtocol
from lca.infrastructure.observability import BoundObservability
from lca.plugins.transport.webserver.handlers.runs.session.session.session import RunSession

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
    role_profile: RoleProfile | None = None
    """Assistant Home persona (ADR-0242 D3); None when no assistant_id."""
    assistant_home_path: str | None = None
    """Assistant Home 绝对路径 (ADR-0242 D4/D5); None when no assistant_id."""


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
        assistant_id = str(getattr(request.session, "assistant_id", "") or "").strip()
        # Resolve the Home path once; both the persona and the tool set read
        # the same Home, so a single catalog lookup serves both (ADR-0242 D3/D4).
        home_path = _home_path_for_assistant(request.scope, assistant_id) if assistant_id else None

        prepared = RunnableBuildRequest(
            assembly=request,
            llm=request.llm_resolver.resolve(),
            tools=tools_from_scope(
                request.scope,
                request.bindings,
                machine_resolver=request.machine_resolver,
                assistant_id=assistant_id,
                home_path=home_path,
            ),
            role_profile=_role_profile_for_assistant(
                request.scope, assistant_id, home_path=home_path
            ),
            assistant_home_path=home_path,
        )
        adapter = self._mode_registry.resolve(request.mode)
        return cast("Agent | Team", await adapter.build(prepared))


def _home_path_for_assistant(scope: Context | None, assistant_id: str) -> str:
    """Resolve an assistant's Home path through the catalog (ADR-0242 D4).

    A non-empty ``assistant_id`` must resolve through the assistant catalog;
    a missing catalog is a run-assembly error rather than a silent policy
    drop. ``POST /runs`` already validates the binding, so this is defensive.
    """
    try:
        catalog = require_capability(scope, ASSISTANT_CATALOG.key)
    except MissingCapabilityError as exc:
        raise RuntimeError(
            "assistant_id is set but the assistant.catalog capability is missing; "
            "cannot resolve the assistant Home"
        ) from exc
    return catalog.get(assistant_id).home_path


def _role_profile_for_assistant(
    scope: Context | None,
    assistant_id: str,
    *,
    home_path: str | None = None,
) -> RoleProfile | None:
    """Resolve an assistant's Home persona into a ``RoleProfile`` (ADR-0242 D3).

    A non-empty ``assistant_id`` must resolve through the assistant catalog;
    a missing catalog is a run-assembly error rather than a silent persona
    drop. ``POST /runs`` already validates the binding, so this is defensive.
    """
    if not assistant_id:
        return None
    if home_path is None:
        home_path = _home_path_for_assistant(scope, assistant_id)
    from lca.plugins.assistant.persona.persona import persona_from_home

    persona = persona_from_home(home_path)
    return RoleProfile(
        role=persona.role,
        goal=persona.goal,
        backstory=persona.backstory,
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
    )


def tools_from_scope(
    scope: Context | None,
    bindings: PlaneBindings | None,
    *,
    machine_resolver: MachineResolver | None = None,
    assistant_id: str = "",
    home_path: str | None = None,
) -> tuple[Tool, ...]:
    """Materialize tools from the booted tools seam; missing seams fail loudly.

    With a non-empty ``assistant_id`` the materialized set is narrowed by the
    assistant Home's ``tools.yaml`` / ``grants.yaml`` (ADR-0242 D4 / I-B3);
    the legacy no-assistant path returns the full set unchanged (I-B8).
    """

    if scope is None:
        return ()
    from lca.infrastructure.runtime_plane.capability_bindings import (
        BindingsViewBuilder,
    )
    from lca.infrastructure.skills.assistant.resolver import resolve_skill_store

    # ``materialize`` consumes a typed ``BindingsView``; the dict form it
    # used to receive was silently downgraded to ``BindingsView()`` inside
    # the g2a factory, so the onlyboxes sandbox (and any other plane-bound
    # capability) never reached the LLM. Wrap the live seam refs first.
    view = BindingsViewBuilder(
        file_store=provider_current(require_capability(scope, "file_store")),
        bindings=bindings,
        sandbox=provider_current(require_capability(scope, "sandbox")),
        search=require_capability(scope, "search"),
        skill_store=resolve_skill_store(scope, assistant_id),
        machine_resolver=machine_resolver,
    ).build()
    tools = tuple(require_capability(scope, "tools").materialize(view))
    assistant_id = assistant_id.strip()
    if not assistant_id:
        return tools
    if home_path is None:
        home_path = _home_path_for_assistant(scope, assistant_id)
    from lca.plugins.assistant.tools import filter_tools_by_assistant

    return filter_tools_by_assistant(tools, home_path)


__all__ = [
    "CognitiveRunnableAssembler",
    "LlmResolver",
    "RunnableAssemblyRequest",
    "RunnableBuildRequest",
    "tools_from_scope",
]
