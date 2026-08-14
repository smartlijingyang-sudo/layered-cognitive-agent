"""Shared default tool set for gateway casting and L4 auto-casting."""

from __future__ import annotations

from lca.contracts.models.core.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.plane.machine import resolve_machine, resolve_machine_transport
from lca.layer0_infra.plane.resolve import ref_of, resolve_plane_bindings, sandbox_ref_from
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.search.tool import WebSearchTool
from lca.layer0_infra.tools.ask_user_question import AskUserQuestionTool
from lca.layer0_infra.tools.computer.tool_set import (
    build_computer_tools,
    build_machine_computer_tools,
)
from lca.layer0_infra.tools.skills.tool_set import build_operational_skill_tools
from lca.layer0_infra.tools.write_file_tool import WriteFileTool

SEARCH_SKILL_TOOL = "search_skill"


def build_g2a_chat_tools(
    store: FileStore | None = None,
    bindings: PlaneBindings | None = None,
) -> list[Tool]:
    """Tools for LobeHub G2A chat — GeneralChatAgent parity.

    Excludes ``search_skill``: LobeHub resolves browsing via ``lobe-web-browsing``
    (our ``web_search`` wire). Skill-store marketplace search is not part of the
    default chat tool surface.
    """
    return [t for t in build_default_tools(store, bindings) if t.name != SEARCH_SKILL_TOOL]


def build_default_tools(
    store: FileStore | None = None,
    bindings: PlaneBindings | None = None,
) -> list[Tool]:
    """Tools available to gateway / auto-casting agents.

    Register the primary face only. secondary is explicit extra_plane.
    """
    file_store = store if store is not None else get_default_file_store()
    bound = bindings if bindings is not None else _ambient_bindings()
    search_tools: list[Tool] = [WebSearchTool()]
    hil_tools: list[Tool] = [AskUserQuestionTool()]
    computer: list[Tool] = []
    sandbox = resolve_sandbox() if ref_of(bound, PlaneKind.SANDBOX) is not None else None
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
            *build_operational_skill_tools(sandbox=skill_sandbox, file_store=file_store),
        ]
    return [
        *search_tools,
        *hil_tools,
        WriteFileTool(store=file_store),
        *build_operational_skill_tools(sandbox=None, file_store=file_store),
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
        return build_computer_tools(sandbox=sandbox, plane=plane, file_store=file_store)  # type: ignore[arg-type]
    transport = resolve_machine_transport(plane.id)
    if transport is None:
        return []
    return build_machine_computer_tools(plane=plane, transport=transport, file_store=file_store)
