"""Shared default tool set for gateway casting and L4 auto-casting.

All tools are now assembled from manifest + executor modules under
``lca/layer0_infra/tools/<name>/``.
"""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.plane.machine import resolve_machine, resolve_machine_transport
from lca.layer0_infra.plane.resolve import ref_of, resolve_plane_bindings, sandbox_ref_from
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.tools import ask_user as ask_user_module
from lca.layer0_infra.tools import lca_computer
from lca.layer0_infra.tools import web_search as web_search_module
from lca.layer0_infra.tools import write_file as write_file_module
from lca.layer0_infra.tools.skills.tool_set import build_operational_skill_tools

SEARCH_SKILL_TOOL = "search_skill"


def build_g2a_chat_tools(
    store: FileStore | None = None,
    bindings: PlaneBindings | None = None,
    **kwargs: object,
) -> list[Tool]:
    """Tools for LobeHub G2A chat — GeneralChatAgent parity."""
    return [t for t in build_default_tools(store, bindings, **kwargs) if t.name != SEARCH_SKILL_TOOL]


def build_default_tools(
    store: FileStore | None = None,
    bindings: PlaneBindings | None = None,
    *,
    sandbox: object | None = None,
    search: object | None = None,
    skill_store: object | None = None,
    fallback: bool = True,
) -> list[Tool]:
    """Tools available to gateway / auto-casting agents.

    *fallback=False* (plugin-tree path): never call module-level
    ``get_default_file_store`` / ``resolve_sandbox``. Missing seams
    skip the corresponding tools instead of growing a second owner.
    """
    file_store = store if store is not None else (get_default_file_store() if fallback else None)
    if bindings is not None:
        bound = bindings
    elif fallback:
        bound = _ambient_bindings()
    else:
        bound = PlaneBindings(primary=None)

    search_tools: list[Tool] = web_search_module.build_tools(search=search)
    hil_tools: list[Tool] = ask_user_module.build_tools()
    computer: list[Tool] = []

    if sandbox is None and fallback:
        sandbox = resolve_sandbox() if ref_of(bound, PlaneKind.SANDBOX) is not None else None

    if file_store is not None:
        if bound.primary is not None:
            computer.extend(_tools_for_ref(bound.primary, file_store, sandbox))
        if bound.secondary is not None:
            computer.extend(_tools_for_ref(bound.secondary, file_store, sandbox))

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


def _ambient_bindings() -> PlaneBindings:
    sandbox = resolve_sandbox()
    sandbox_ref = sandbox_ref_from(sandbox) if sandbox is not None else None
    return resolve_plane_bindings(resolve_machine(), sandbox_ref)


def _tools_for_ref(
    plane: PlaneRef,
    file_store: FileStore,
    sandbox: object | None,
) -> list[Tool]:
    if plane.kind is PlaneKind.SANDBOX:
        if sandbox is None:
            return []
        return lca_computer.build_computer_tools(
            sandbox=sandbox, plane=plane, file_store=file_store
        )  # type: ignore[arg-type]
    transport = resolve_machine_transport(plane.id)
    if transport is None:
        return []
    return lca_computer.build_machine_computer_tools(
        plane=plane, transport=transport, file_store=file_store
    )
