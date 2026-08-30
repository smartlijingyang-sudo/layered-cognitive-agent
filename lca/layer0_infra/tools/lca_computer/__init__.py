"""lca-computer tool module — manifest + executor + observations (LobeHub alignment)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from lca.contracts.protocols import Sandbox, Tool
from lca.contracts.protocols.infra import MachineTransport
from lca.layer0_infra.computer.machine import MachineComputer
from lca.layer0_infra.computer.ops import ComputerOps
# Lazy import SandboxComputer below to break circular: computer ↔ tools.
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.tools.builder import build_tools_from_manifest
from lca.layer0_infra.tools.lca_computer.executor import LcaComputerExecutor, LcaSandboxExecutor
from lca.layer0_infra.tools.lca_computer.manifest import (
    CLOUD_SANDBOX_MANIFEST,
    MACHINE_MANIFEST,
    MANIFEST,
)
from lca.layer0_infra.tools.lca_computer.observations import build_computer_observation
from lca.layer0_infra.tools.lca_computer.types import ApiName

__all__ = [
    "CLOUD_SANDBOX_MANIFEST",
    "MACHINE_MANIFEST",
    "MANIFEST",
    "ApiName",
    "LcaComputerExecutor",
    "LcaSandboxExecutor",
    "build_computer_tools",
    "build_machine_computer_tools",
]


def _computer_obs_builder(store: FileStore) -> Callable[..., Any]:
    """Return an observation builder bound to a FileStore."""

    def _build(raw: Any, tool_name: str, start: float) -> Any:
        from lca.layer0_infra.computer.op_result import ComputerOpResult

        if isinstance(raw, ComputerOpResult):
            return build_computer_observation(raw, tool_name=tool_name, start=start, store=store)
        return raw

    return _build


def _invoke_via_executor(
    executor: LcaComputerExecutor, api_name: str, params: dict[str, Any]
) -> Any:
    return executor.invoke(api_name, params)


def build_computer_tools(
    *,
    sandbox: Sandbox | None = None,
    plane: Any = None,
    ops: ComputerOps | None = None,
    file_store: FileStore | None = None,
) -> list[Tool]:
    """Build cloud-sandbox computer tools (13 APIs, ``lobe-cloud-sandbox``)."""
    if file_store is None:
        raise TypeError("build_computer_tools requires an explicit file_store")
    store = file_store
    runtime: ComputerOps
    if ops is not None:
        runtime = ops
    elif sandbox is not None:
        from lca.layer0_infra.plane.resolve import sandbox_ref_from

        from lca.layer0_infra.computer.sandbox_computer import SandboxComputer
        runtime = SandboxComputer(
            plane=plane or sandbox_ref_from(sandbox),
            sandbox=sandbox,
            store=store,
        )
    else:
        raise TypeError("build_computer_tools requires sandbox or ops")

    if hasattr(runtime, "execute_code") and hasattr(runtime, "export_file"):
        executor: LcaSandboxExecutor | LcaComputerExecutor = LcaSandboxExecutor(runtime)
    else:
        executor = LcaComputerExecutor(runtime)

    return build_tools_from_manifest(
        CLOUD_SANDBOX_MANIFEST,
        executor,
        invoke_fn=cast(
            "Callable[[object, str, dict[str, Any]], Awaitable[Any]]", _invoke_via_executor
        ),
        observation_builder=_computer_obs_builder(store),
    )


def build_machine_computer_tools(
    *,
    plane: Any,
    transport: MachineTransport,
    file_store: FileStore | None = None,
) -> list[Tool]:
    """Build machine-prefixed tools (11 APIs — no executeCode/exportFile)."""
    if file_store is None:
        raise TypeError("build_machine_computer_tools requires an explicit file_store")
    store = file_store
    computer = MachineComputer(plane, transport, store=store)
    executor = LcaComputerExecutor(computer)

    return build_tools_from_manifest(
        MACHINE_MANIFEST,
        executor,
        invoke_fn=cast(
            "Callable[[object, str, dict[str, Any]], Awaitable[Any]]", _invoke_via_executor
        ),
        observation_builder=_computer_obs_builder(store),
        name_prefix="local_",
    )
