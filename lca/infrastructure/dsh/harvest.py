"""Publish machine ``outputs_dir`` files into FileStore + run workspace (device parity)."""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.plane import PlaneRef
from lca.infrastructure.computer.machine import MachineTransport
from lca.infrastructure.computer.machine_harvest import harvest_plane_outputs
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.workspace.scope import get_run_workspace


async def harvest_machine_outputs(
    *,
    machine: PlaneRef,
    transport: MachineTransport,
    store: FileStore,
) -> list[dict[str, Any]]:
    """Same binary harvest as MachineComputer — FileStore parts the UI already knows."""
    return await harvest_plane_outputs(
        computer_op=transport.computer_op,
        plane=machine,
        store=store,
        tool_name="local_writeFile",
    )


async def record_dsh_harvest(file_parts: list[dict[str, Any]]) -> None:
    """Append harvested parts to the active run workspace ledger."""
    if not file_parts:
        return
    workspace = get_run_workspace()
    if workspace is None:
        return
    workspace.artifacts.record_harvest(
        file_parts,
        stdout="",
        tool_name="dsh",
        command="",
    )
