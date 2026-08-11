"""Shared default tool set for gateway casting and L4 auto-casting."""

from __future__ import annotations

from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.search.tool import WebSearchTool
from lca.layer0_infra.tools.ask_user_question import AskUserQuestionTool
from lca.layer0_infra.tools.computer.tool_set import build_computer_tools
from lca.layer0_infra.tools.skills.tool_set import build_operational_skill_tools
from lca.layer0_infra.tools.write_file_tool import WriteFileTool

SEARCH_SKILL_TOOL = "search_skill"


def build_g2a_chat_tools(store: FileStore | None = None) -> list[Tool]:
    """Tools for LobeHub G2A chat — GeneralChatAgent parity.

    Excludes ``search_skill``: LobeHub resolves browsing via ``lobe-web-browsing``
    (our ``web_search`` wire). Skill-store marketplace search is not part of the
    default chat tool surface.
    """
    return [t for t in build_default_tools(store) if t.name != SEARCH_SKILL_TOOL]


def build_default_tools(store: FileStore | None = None) -> list[Tool]:
    """Tools available to gateway / auto-casting agents.

    With Onlyboxes configured (Computer Use / LobeHub cloud-sandbox parity):
    - 13 computer tools — executeCode, runCommand, listFiles, readFile, …
    - operational skill tools — search / import / activate / read / execScript

    Without sandbox: host ``write_file`` + skill tools (no exec).

    Legacy ``sandbox_inspect`` / ``sandbox_execute`` are internal-only (tests);
    agents use ``list_files`` / ``read_file`` / ``run_command`` instead.
    """
    file_store = store if store is not None else get_default_file_store()
    sandbox = resolve_sandbox()
    search_tools: list[Tool] = [WebSearchTool()]
    hil_tools: list[Tool] = [AskUserQuestionTool()]
    if sandbox is not None:
        return [
            *search_tools,
            *hil_tools,
            *build_computer_tools(sandbox=sandbox, file_store=file_store),
            *build_operational_skill_tools(sandbox=sandbox, file_store=file_store),
        ]
    return [
        *search_tools,
        *hil_tools,
        WriteFileTool(store=file_store),
        *build_operational_skill_tools(sandbox=None, file_store=file_store),
    ]
