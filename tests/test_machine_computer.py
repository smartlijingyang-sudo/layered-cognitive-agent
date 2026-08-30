"""MachineComputer talks only to a transport. No Sandbox, no remap."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.contracts.models.core.result import ApprovalPendingError
from lca.infrastructure.computer.machine import MachineComputer
from lca.infrastructure.file_store import LocalFileStore
from lca.infrastructure.tools.lca_computer.observations import build_computer_observation
from lca.cognition.body.tool_result_preview import tool_files


class _FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.writes: list[tuple[dict[str, bytes | str], dict[str, Any]]] = []

    async def computer_op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> dict[str, Any]:
        del timeout_s
        self.calls.append((op, args))
        return {"success": True, "content": "ok", "files": []}

    async def write_files(self, files: dict[str, bytes | str], **kwargs: Any) -> Any:
        self.writes.append((files, kwargs))
        return None


_PDF_BYTES = b"%PDF-1.4 binary\xff\x00trailer"


class _SidecarTransport:
    """Mirrors today's CLI: listFiles nests names under state; exportFile is b64 content."""

    def __init__(self, blobs: dict[str, bytes]) -> None:
        self.blobs = blobs
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.writes: list[tuple[dict[str, bytes | str], dict[str, Any]]] = []

    async def computer_op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> dict[str, Any]:
        del timeout_s
        self.calls.append((op, args))
        if op == "runCommand":
            return {"success": True, "content": "PDF generated successfully: outputs/50类型.pdf"}
        if op == "listFiles":
            names = [{"name": name, "isDirectory": False} for name in self.blobs]
            return {
                "success": True,
                "content": json.dumps(names, ensure_ascii=False),
                "state": {"files": names},
            }
        if op == "exportFile":
            name = str(args.get("path") or "").replace("\\", "/").rsplit("/", 1)[-1]
            data = self.blobs.get(name)
            if data is None:
                return {"success": False, "error": f"missing {name}"}
            return {"success": True, "content": base64.b64encode(data).decode("ascii")}
        if op == "readFile":
            raise AssertionError("binary harvest must not use text readFile")
        if op == "writeFile":
            return {"success": False, "error": "path /home/lca-sandbox/.lca/exec_x.py is denied"}
        return {"success": True, "content": "ok", "files": []}

    async def write_files(self, files: dict[str, bytes | str], **kwargs: Any) -> Any:
        self.writes.append((files, kwargs))
        return {"success": True}


def _store(tmp_path: Path) -> LocalFileStore:
    return LocalFileStore(tmp_path / "files")


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
async def test_relative_path_joins_root(tmp_path: Path) -> None:
    transport = _FakeTransport()
    computer = MachineComputer(_plane(), transport, store=_store(tmp_path))
    await computer.read_file(path="notes.txt")
    assert transport.calls[0][1]["path"] == "/home/lca-sandbox/notes.txt"


@pytest.mark.asyncio
async def test_out_of_root_raises_hitl(tmp_path: Path) -> None:
    computer = MachineComputer(_plane(), _FakeTransport(), store=_store(tmp_path))
    with pytest.raises(ApprovalPendingError):
        await computer.read_file(path="/mnt/data/x")


@pytest.mark.asyncio
async def test_execute_code_available_on_machine(tmp_path: Path) -> None:
    """MachineComputer now supports execute_code (temp file + interpreter)."""
    computer = MachineComputer(_plane(), _FakeTransport(), store=_store(tmp_path))
    assert hasattr(computer, "execute_code")


@pytest.mark.asyncio
async def test_run_command_sends_timeout_s_and_timeout(tmp_path: Path) -> None:
    transport = _FakeTransport()
    computer = MachineComputer(_plane(), transport, store=_store(tmp_path))
    await computer.run_command(command="false", timeout_s=15)
    op, args = transport.calls[0]
    assert op == "runCommand"
    assert args["timeout_s"] == 15
    assert args["timeout"] == 15


@pytest.mark.asyncio
async def test_run_command_publishes_pdf_as_canonical_file_part(tmp_path: Path) -> None:
    """Machine outputs/ harvest must reuse sandbox FileStore parts (name + /files url)."""
    store = LocalFileStore(tmp_path / "files")
    transport = _SidecarTransport({"50类型.pdf": _PDF_BYTES})
    computer = MachineComputer(_plane(), transport, store=store)

    result = await computer.run_command(command="python3 make_pdf.py")
    files = result.state.get("files") or []
    assert files, "outputs/ PDF must land on ComputerOpResult.state['files']"
    part = files[0]
    assert part["name"] == "50类型.pdf"
    assert str(part["url"]).startswith("/files/")
    assert part["mimeType"] == "application/pdf"
    attachment_id = str(part["attachmentId"])
    assert store.read_bytes(attachment_id) == _PDF_BYTES

    obs = build_computer_observation(result, tool_name="runCommand", start=0.0, store=store)
    invoked = tool_files(obs)
    assert invoked and invoked[0]["name"] == "50类型.pdf"
    assert invoked[0]["url"] == part["url"]


@pytest.mark.asyncio
async def test_execute_code_uses_system_write_not_denied_lca_path(tmp_path: Path) -> None:
    """Temp scripts are infrastructure: write_files (system), not writeFile (.lca denied)."""
    transport = _SidecarTransport({})
    computer = MachineComputer(_plane(), transport, store=_store(tmp_path))
    result = await computer.execute_code(code="print(1)")
    assert result.success
    assert transport.writes, "execute_code must use MachineTransport.write_files"
    assert not any(op == "writeFile" for op, _ in transport.calls)
