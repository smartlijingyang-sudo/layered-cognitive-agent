"""Shared default tool set for gateway casting and L4 auto-casting (ADR-0044)."""

from __future__ import annotations

from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.sandbox.factory import resolve_sandbox
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer0_infra.tools.sandbox_code_tool import SandboxCodeTool
from lca.layer0_infra.tools.write_file_tool import WriteFileTool


def build_default_tools(
    store: FileStore | None = None,
    *,
    include_sandbox_mock: bool = False,
) -> list[Tool]:
    """Tools available to gateway / auto-casting agents.

    Sandbox tool is included only when a real backend is selected
    (``E2B_API_KEY`` / ``LCA_SANDBOX_BACKEND=local``) or
    ``include_sandbox_mock`` for explicit offline demos. No silent Mock
    in production wiring (ADR-0044).
    """
    file_store = store if store is not None else get_default_file_store()
    tools: list[Tool] = [
        CalculatorTool(),
        WriteFileTool(store=file_store),
    ]
    sandbox = resolve_sandbox(prefer_mock=include_sandbox_mock)
    if sandbox is not None:
        tools.append(SandboxCodeTool(sandbox=sandbox, store=file_store))
    return tools
