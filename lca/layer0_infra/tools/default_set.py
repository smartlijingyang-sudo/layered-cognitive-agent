"""Shared default tool set for gateway casting and L4 auto-casting."""

from __future__ import annotations

from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.tools.sandbox_code_tool import SandboxCodeTool
from lca.layer0_infra.tools.write_file_tool import WriteFileTool


def build_default_tools(store: FileStore | None = None) -> list[Tool]:
    """Tools available to gateway / auto-casting agents.

    Production defaults: ``write_file`` (downloadable products) + ``run_sandbox_code``
    when Onlyboxes is configured. Arithmetic / weather demos are not auto-mounted —
    opt in via scenario tooling or explicit Agent(tools=...).
    """
    file_store = store if store is not None else get_default_file_store()
    tools: list[Tool] = [
        WriteFileTool(store=file_store),
    ]
    sandbox = resolve_sandbox()
    if sandbox is not None:
        tools.append(SandboxCodeTool(sandbox=sandbox, store=file_store))
    return tools
