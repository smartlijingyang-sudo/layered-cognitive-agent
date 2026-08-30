"""Shared default tool set for gateway casting and L4 auto-casting.

All tools are now assembled from manifest + executor modules under
``lca/infrastructure/tools/<name>/``.
"""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.contracts.protocols import Tool
from lca.contracts.protocols.runtime.infra import MachineResolver, Sandbox
from lca.contracts.protocols.memory.operational_skills import SkillPackageInstaller
from lca.infrastructure.capability.search import SearchService
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.plane.resolve import ref_of, resolve_plane_bindings, sandbox_ref_from
from lca.infrastructure.sandbox.factory import resolve_sandbox
from lca.infrastructure.tools import ask_user as ask_user_module
from lca.infrastructure.tools import lca_computer
from lca.infrastructure.tools import web_search as web_search_module
from lca.infrastructure.tools import write_file as write_file_module
from lca.infrastructure.tools.skills.tool_set import build_operational_skill_tools

SEARCH_SKILL_TOOL = "search_skill"


def build_g2a_chat_tools(
    store: FileStore | None = None,
    bindings: PlaneBindings | None = None,
    *,
    sandbox: Sandbox | None = None,
    search: SearchService | None = None,
    skill_store: SkillPackageInstaller | None = None,
    machine_resolver: MachineResolver | None = None,
    fallback: bool = True,
) -> list[Tool]:
    """Tools for LobeHub G2A chat — GeneralChatAgent parity."""
    return [
        t
        for t in build_default_tools(
            store,
            bindings,
            sandbox=sandbox,
            search=search,
            skill_store=skill_store,
            machine_resolver=machine_resolver,
            fallback=fallback,
        )
        if t.name != SEARCH_SKILL_TOOL
    ]


def build_default_tools(
    store: FileStore | None = None,
    bindings: PlaneBindings | None = None,
    *,
    sandbox: Sandbox | None = None,
    search: SearchService | None = None,
    skill_store: SkillPackageInstaller | None = None,
    machine_resolver: MachineResolver | None = None,
    fallback: bool = True,
) -> list[Tool]:
    """Tools available to gateway / auto-casting agents.

    Missing explicit FileStore seams skip corresponding file tools instead
    of constructing an ambient storage owner.
    """
    file_store = store
    if bindings is not None:
        bound = bindings
    elif fallback:
        bound = _ambient_bindings(machine_resolver)
    else:
        bound = PlaneBindings(primary=None)

    search_tools: list[Tool] = web_search_module.build_tools(search=search)
    hil_tools: list[Tool] = ask_user_module.build_tools()
    computer: list[Tool] = []

    if sandbox is None and fallback:
        sandbox = resolve_sandbox() if ref_of(bound, PlaneKind.SANDBOX) is not None else None

    if file_store is not None:
        if bound.primary is not None:
            computer.extend(_tools_for_ref(bound.primary, file_store, sandbox, machine_resolver))
        if bound.secondary is not None:
            computer.extend(_tools_for_ref(bound.secondary, file_store, sandbox, machine_resolver))

    if computer:
        skill_sandbox = (
            sandbox
            if bound.primary is not None and bound.primary.kind is PlaneKind.SANDBOX
            else None
        )
        return [
            *search_tools,
            *hil_tools,
            *computer,
            *build_operational_skill_tools(
                sandbox=skill_sandbox, file_store=file_store, store=skill_store
            ),
        ]

    write_tools: list[Tool] = (
        write_file_module.build_tools(store=file_store) if file_store is not None else []
    )
    return [
        *search_tools,
        *hil_tools,
        *write_tools,
        *build_operational_skill_tools(sandbox=None, file_store=file_store, store=skill_store),
    ]


def _ambient_bindings(machine_resolver: MachineResolver | None) -> PlaneBindings:
    sandbox = resolve_sandbox()
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    machine = machine_resolver.resolve_machine() if machine_resolver is not None else None
    return resolve_plane_bindings(machine, sandbox_ref)


def _tools_for_ref(
    plane: PlaneRef,
    file_store: FileStore,
    sandbox: Sandbox | None,
    machine_resolver: MachineResolver | None,
) -> list[Tool]:
    if plane.kind is PlaneKind.SANDBOX:
        if sandbox is None:
            return []
        return lca_computer.build_computer_tools(
            sandbox=sandbox, plane=plane, file_store=file_store
        )
    transport = (
        machine_resolver.resolve_transport(plane.id) if machine_resolver is not None else None
    )
    if transport is None:
        return []
    return lca_computer.build_machine_computer_tools(
        plane=plane, transport=transport, file_store=file_store
    )
