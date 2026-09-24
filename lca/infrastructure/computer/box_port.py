"""员工电脑（我的电脑）专属沙箱执行端口协议契约（ADR-0248 §3.2 / s04）。

该端口隔离员工机的文件与命令操作，提供容器沙箱与本地受限沙箱的双向抽象。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class BoxCommandResult:
    """员工机沙箱命令执行结果契约。"""

    stdout: str
    stderr: str
    returncode: int


@runtime_checkable
class BoxExecutionPort(Protocol):
    """员工电脑专属沙箱执行端口协议。"""

    async def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """安全读取沙箱内文件内容。"""
        ...

    async def write_file(
        self,
        path: str,
        content: str,
        create_directories: bool = True,
    ) -> str:
        """安全写入沙箱内文件内容。"""
        ...

    async def list_files(
        self,
        path: str = ".",
        max_depth: int = 1,
    ) -> list[str]:
        """安全列出沙箱内目录条目。"""
        ...

    async def run_command(
        self,
        command: str,
        timeout_s: int = 30,
    ) -> BoxCommandResult:
        """在隔离沙箱环境中执行 Shell 命令。"""
        ...


__all__ = ["BoxCommandResult", "BoxExecutionPort"]
