"""LobeHub cloud-sandbox tool set — Manus / Computer Use parity."""

from __future__ import annotations

import time
from typing import Any

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.protocols import Sandbox, Tool
from lca.layer0_infra.computer.machine import MachineComputer, MachineTransport
from lca.layer0_infra.computer.ops import ComputerOps
from lca.layer0_infra.computer.sandbox_computer import SandboxComputer
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
    "build_machine_computer_tools",
]

_SANDBOX_ONLY = frozenset({EXECUTE_CODE, EXPORT_FILE})


def _instantiate_computer_tool(
    spec: ComputerToolSpec,
    *,
    ops: ComputerOps,
    store: FileStore,
    name: str | None = None,
) -> Tool:
    tool_name = name if name is not None else spec.name

    async def execute(_self: Tool, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        result = await spec.handler(ops, args)  # type: ignore[arg-type]
        extra_obs = build_computer_observation(
            result, tool_name=tool_name, start=start, store=store
        )
        plane = getattr(ops, "plane", None)
        if isinstance(plane, PlaneRef) and isinstance(extra_obs.extra, dict):
            extra_obs.extra["plane"] = {
                "kind": plane.kind.value,
                "id": plane.id,
                "root": plane.root,
            }
        return extra_obs

    tool_cls = type(
        f"ComputerTool_{tool_name}",
        (Tool,),
        {
            "name": tool_name,
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
    sandbox: Sandbox | None = None,
    plane: PlaneRef | None = None,
    ops: ComputerOps | None = None,
    file_store: FileStore | None = None,
) -> list[Tool]:
    store = file_store if file_store is not None else get_default_file_store()
    runtime: ComputerOps
    if ops is not None:
        runtime = ops
    elif sandbox is not None:
        from lca.layer0_infra.plane.resolve import sandbox_ref_from

        runtime = SandboxComputer(
            plane=plane or sandbox_ref_from(sandbox),
            sandbox=sandbox,
            store=store,
        )
    else:
        raise TypeError("build_computer_tools requires sandbox or ops")
    return [
        _instantiate_computer_tool(spec, ops=runtime, store=store) for spec in _COMPUTER_TOOL_SPECS
    ]


def build_machine_computer_tools(
    *,
    plane: PlaneRef,
    transport: MachineTransport,
    file_store: FileStore | None = None,
) -> list[Tool]:
    store = file_store if file_store is not None else get_default_file_store()
    computer = MachineComputer(plane, transport, store=store)
    return [
        _instantiate_computer_tool(
            spec,
            ops=computer,
            store=store,
            name=f"local_{spec.name}",
        )
        for spec in _COMPUTER_TOOL_SPECS
        if spec.name not in _SANDBOX_ONLY
    ]
