"""Regression: writeFile/editFile must reject installed skill packages.

``run_755719d1a9d5`` 中模型用 5 次 writeFile 替换了
``~/.lca/assistants/asst_c8b83acb1920/skills/psychological-counselor/SKILL.md``，
索引 digest 与 artifact_state（verified）纹丝不动——绕行无迹可寻。
修复后通用文件写在调用后端前就拒绝这类路径，模型收到明确错误并应改用
create_assistant_skill / edit_assistant_skill；读路径不受影响。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.computer.op.result import ComputerOpResult
from lca.infrastructure.path.policy import validate_writable_file
from lca.infrastructure.tools.lca_computer.executor import LcaComputerExecutor

_HOME = "/home/lichao/.lca/assistants/asst_c8b83acb1920"
_PKG = f"{_HOME}/skills/psychological-counselor"


class _RecordingOps:
    def __init__(self) -> None:
        self.plane = PlaneRef(
            id="p", label="p", kind=PlaneKind.MACHINE, root="/tmp", outputs_dir="/tmp/outputs", platform="linux"  # noqa: S108
        )
        self.writes: list[str] = []
        self.reads: list[str] = []

    async def write_file(self, *, path: str, content: str, create_directories: bool = True) -> ComputerOpResult:
        self.writes.append(path)
        return ComputerOpResult(success=True, content="ok", state={})

    async def edit_file(self, *, path: str, search: str, replace: str, replace_all: bool = False) -> ComputerOpResult:
        self.writes.append(path)
        return ComputerOpResult(success=True, content="ok", state={})

    async def read_file(self, *, path: str, start_line: int | None = None, end_line: int | None = None) -> ComputerOpResult:
        self.reads.append(path)
        return ComputerOpResult(success=True, content="body", state={})


def test_write_file_rejects_skill_package_without_calling_backend() -> None:
    ops = _RecordingOps()
    ex = LcaComputerExecutor(ops)
    result = asyncio.run(
        ex.write_file({"path": f"{_PKG}/SKILL.md", "content": "# tampered\n"})
    )
    assert not result.success
    assert "create_assistant_skill" in (result.error or "")
    assert "edit_assistant_skill" in (result.error or "")
    assert ops.writes == []


def test_edit_file_rejects_skill_package_without_calling_backend() -> None:
    ops = _RecordingOps()
    ex = LcaComputerExecutor(ops)
    result = asyncio.run(
        ex.edit_file({"path": f"{_PKG}/SKILL.md", "search": "a", "replace": "b"})
    )
    assert not result.success
    assert "create_assistant_skill" in (result.error or "")
    assert ops.writes == []


def test_read_file_on_skill_package_is_not_blocked() -> None:
    ops = _RecordingOps()
    ex = LcaComputerExecutor(ops)
    result = asyncio.run(ex.read_file({"path": f"{_PKG}/SKILL.md"}))
    assert result.success
    assert ops.reads == [f"{_PKG}/SKILL.md"]


def test_write_file_allows_workspace_skill_md() -> None:
    ops = _RecordingOps()
    ex = LcaComputerExecutor(ops)
    result = asyncio.run(
        ex.write_file({"path": f"{_HOME}/workspace/SKILL.md", "content": "draft"})
    )
    assert result.success
    assert ops.writes == [f"{_HOME}/workspace/SKILL.md"]


def test_validate_writable_file_rejects_skill_package() -> None:
    decision = validate_writable_file(Path(f"{_PKG}/SKILL.md"))
    assert not decision.accept
    assert "create_assistant_skill" in decision.error

    ok = validate_writable_file(Path(f"{_HOME}/workspace/SKILL.md"))
    assert ok.accept
