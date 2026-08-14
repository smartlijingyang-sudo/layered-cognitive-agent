"""SandboxComputer binds PlaneRef + Sandbox. No machine transport."""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.models.core.plane import PlaneKind, PlaneRef
from lca.layer0_infra.computer.sandbox_computer import SandboxComputer, normalize_sandbox_path


class _FakeSandbox:
    name = "test-sandbox"


def _plane() -> PlaneRef:
    return PlaneRef(
        id="sb-1",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
        platform="linux",
    )


def test_normalize_relative_to_plane_root() -> None:
    assert normalize_sandbox_path("notes.txt", "/mnt/data") == "/mnt/data/notes.txt"
    assert normalize_sandbox_path("./out/a.pdf", "/mnt/data") == "/mnt/data/out/a.pdf"
    assert normalize_sandbox_path("", "/mnt/data") == "/mnt/data"


def test_has_execute_code_and_export_file() -> None:
    computer = SandboxComputer(plane=_plane(), sandbox=_FakeSandbox(), store=_FakeStore())  # type: ignore[arg-type]
    assert hasattr(computer, "execute_code")
    assert hasattr(computer, "export_file")
    assert computer.plane.root == "/mnt/data"


class _FakeStore:
    def put(self, **kwargs: Any) -> Any:
        del kwargs
        raise NotImplementedError

    def get(self, attachment_id: str) -> None:
        del attachment_id
        return None

    def read_bytes(self, attachment_id: str) -> None:
        del attachment_id
        return None


@pytest.mark.asyncio
async def test_list_files_uses_plane_root_for_empty_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    async def fake_guest_op(self: SandboxComputer, script: str, **kwargs: Any) -> Any:
        del kwargs
        captured.append(script)
        from lca.layer0_infra.computer.op_result import ComputerOpResult

        return ComputerOpResult(success=True, content="ok", state={"success": True})

    monkeypatch.setattr(SandboxComputer, "_guest_op", fake_guest_op)
    computer = SandboxComputer(plane=_plane(), sandbox=_FakeSandbox(), store=_FakeStore())  # type: ignore[arg-type]
    await computer.list_files(directory_path="")
    assert "/mnt/data" in captured[0]
