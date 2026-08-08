"""Production tool set for gateway-composed agents (Phase C)."""

from __future__ import annotations

from lca.contracts.protocols import Tool
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.tools.calculator_tool import CalculatorTool
from lca.layer0_infra.tools.write_file_tool import WriteFileTool


def production_tools(store: FileStore | None = None) -> list[Tool]:
    """Tools available to gateway / auto-casting agents."""
    file_store = store if store is not None else get_default_file_store()
    return [
        CalculatorTool(),
        WriteFileTool(store=file_store),
    ]
