"""Shared computer operation Protocol — two adapters, no kind switch."""

from __future__ import annotations

from typing import Protocol

from lca.contracts.models.core.plane import PlaneRef
from lca.layer0_infra.computer.op_result import ComputerOpResult


class ComputerOps(Protocol):
    """File/shell/search — shared by machine and sandbox adapters."""

    plane: PlaneRef

    async def list_files(self, *, directory_path: str) -> ComputerOpResult: ...

    async def read_file(
        self,
        *,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ComputerOpResult: ...

    async def write_file(
        self,
        *,
        path: str,
        content: str,
        create_directories: bool = True,
    ) -> ComputerOpResult: ...

    async def edit_file(
        self,
        *,
        path: str,
        search: str,
        replace: str,
        replace_all: bool = False,
    ) -> ComputerOpResult: ...

    async def search_files(
        self,
        *,
        directory: str,
        keyword: str = "",
        file_type: str = "",
        modified_after: str = "",
        modified_before: str = "",
    ) -> ComputerOpResult: ...

    async def move_files(self, *, operations: list[dict[str, str]]) -> ComputerOpResult: ...

    async def grep_content(
        self,
        *,
        pattern: str,
        directory: str,
        file_pattern: str = "",
        recursive: bool = True,
    ) -> ComputerOpResult: ...

    async def glob_files(self, *, pattern: str, directory: str = "") -> ComputerOpResult: ...

    async def run_command(
        self,
        *,
        command: str,
        description: str = "",
        background: bool = False,
        timeout_s: int = 60,
    ) -> ComputerOpResult: ...

    async def get_command_output(
        self,
        *,
        command_id: str,
        timeout_s: int = 60,
    ) -> ComputerOpResult: ...

    async def kill_command(self, *, command_id: str) -> ComputerOpResult: ...

    async def execute_code(
        self,
        *,
        code: str,
        language: str = "python",
        description: str = "",
        timeout_s: int = 60,
    ) -> ComputerOpResult: ...


class SandboxExecOps(ComputerOps, Protocol):
    """Sandbox-only: explicit file export (code execution is shared now)."""

    async def export_file(self, *, path: str) -> ComputerOpResult: ...
