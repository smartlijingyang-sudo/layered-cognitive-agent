"""LobeHub cloud-sandbox tool set — Manus / Computer Use parity."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Sandbox, Tool
from lca.layer0_infra.computer.runtime import ComputerRuntime
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.tools.computer.observations import build_computer_observation
from lca.layer0_infra.tools.computer.specs import (
    _COMPUTER_TOOL_SPECS,
    EDIT_FILE,
    EXECUTE_CODE,
    EXPORT_FILE,
    GET_COMMAND_OUTPUT,
    GLOB_FILES,
    GREP_CONTENT,
    KILL_COMMAND,
    LIST_FILES,
    MOVE_FILES,
    READ_FILE,
    RUN_COMMAND,
    SEARCH_FILES,
    WRITE_FILE,
    ComputerToolSpec,
)

__all__ = [
    "EDIT_FILE",
    "EXECUTE_CODE",
    "EXPORT_FILE",
    "GET_COMMAND_OUTPUT",
    "GLOB_FILES",
    "GREP_CONTENT",
    "KILL_COMMAND",
    "LIST_FILES",
    "MOVE_FILES",
    "READ_FILE",
    "RUN_COMMAND",
    "SEARCH_FILES",
    "WRITE_FILE",
    "ComputerToolSpec",
    "build_computer_tools",
]


def _instantiate_computer_tool(
    spec: ComputerToolSpec,
    *,
    sandbox: Sandbox,
    store: FileStore,
) -> Tool:
    runtime = ComputerRuntime(sandbox=sandbox, store=store)

    async def execute(_self: Tool, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        result = await spec.handler(runtime, args)
        return build_computer_observation(result, tool_name=spec.name, start=start, store=store)

    tool_cls = type(
        f"ComputerTool_{spec.name}",
        (Tool,),
        {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
            "is_idempotent": spec.is_idempotent,
            "default_timeout_s": spec.default_timeout_s,
            "execute": execute,
        },
    )
    return tool_cls()  # type: ignore[no-any-return]


def build_computer_tools(
    *,
    sandbox: Sandbox,
    file_store: FileStore | None = None,
) -> list[Tool]:
    store = file_store if file_store is not None else get_default_file_store()
    return [
        _instantiate_computer_tool(spec, sandbox=sandbox, store=store)
        for spec in _COMPUTER_TOOL_SPECS
    ]
