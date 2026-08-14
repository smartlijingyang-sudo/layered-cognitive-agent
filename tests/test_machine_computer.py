"""MachineComputer talks only to a transport. No Sandbox, no remap."""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.models.core.result import ApprovalPendingError
from lca.layer0_infra.computer.machine import MachineComputer


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def computer_op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> dict[str, Any]:
        del timeout_s
        self.calls.append((op, args))
        return {"success": True, "content": "ok", "files": []}

    async def write_files(self, files: dict[str, bytes | str], **kwargs: Any) -> Any:
        del files, kwargs
        return None


def _plane() -> PlaneRef:
    return PlaneRef(
        id="dev-1",
        label="box",
        kind=PlaneKind.MACHINE,
        root="/home/lca-sandbox",
        outputs_dir="/home/lca-sandbox/outputs",
        platform="linux",
    )


@pytest.mark.asyncio
async def test_relative_path_joins_root() -> None:
    transport = _FakeTransport()
    computer = MachineComputer(_plane(), transport)
    await computer.read_file(path="notes.txt")
    assert transport.calls[0][1]["path"] == "/home/lca-sandbox/notes.txt"


@pytest.mark.asyncio
async def test_out_of_root_raises_hitl() -> None:
    computer = MachineComputer(_plane(), _FakeTransport())
    with pytest.raises(ApprovalPendingError):
        await computer.read_file(path="/mnt/data/x")


@pytest.mark.asyncio
async def test_no_execute_code_on_class() -> None:
    assert not hasattr(MachineComputer(_plane(), _FakeTransport()), "execute_code")
