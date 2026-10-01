"""Regression: writeFile must reject standing memory files.

``run_ab78aeb6eabf`` 中 writeFile 把 ``~/.lca/assistants/<id>/memory/USER.md``
整个覆盖成模板内容，没有任何审批。修复后 writeFile 在调用后端前就拒绝
这类路径，模型收到明确错误并应改用 memory_add。
"""

from __future__ import annotations

import asyncio
from typing import Any

from lca.contracts.models.core.execution.local_exec import AccessScope
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.computer.op.result import ComputerOpResult
from lca.infrastructure.path.policy import validate_writable_file
from lca.infrastructure.tools.lca_computer.executor import LcaComputerExecutor
from lca.infrastructure.tools.lca_computer.types import ApiName


class _RecordingOps:
    def __init__(self) -> None:
        self.plane = PlaneRef(
            id="p", label="p", kind=PlaneKind.MACHINE, root="/tmp", outputs_dir="/tmp/outputs", platform="linux"
        )
        self.writes: list[str] = []

    async def write_file(self, *, path: str, content: str, create_directories: bool = True) -> ComputerOpResult:
        self.writes.append(path)
        return ComputerOpResult(success=True, content="ok", state={})


def test_write_file_rejects_standing_path_without_calling_backend() -> None:
    ops = _RecordingOps()
    ex = LcaComputerExecutor(ops)
    result = asyncio.run(
        ex.write_file(
            {
                "path": "/home/lichao/.lca/assistants/asst_x/memory/USER.md",
                "content": "# USER\n萨莉亚",
            }
        )
    )
    assert not result.success
    assert "memory_add" in (result.error or "")
    assert ops.writes == []


def test_write_file_allows_workspace_path() -> None:
    ops = _RecordingOps()
    ex = LcaComputerExecutor(ops)
    result = asyncio.run(
        ex.write_file({"path": "/tmp/report.md", "content": "hello"})
    )
    assert result.success
    assert ops.writes == ["/tmp/report.md"]


def test_validate_writable_file_rejects_standing_path() -> None:
    from pathlib import Path

    decision = validate_writable_file(Path("/home/u/.lca/assistants/asst_x/memory/USER.md"))
    assert not decision.accept
    assert "memory_add" in decision.error

    ok = validate_writable_file(Path("/tmp/ok.md"))
    assert ok.accept