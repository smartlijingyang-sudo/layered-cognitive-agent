"""ComputerRuntime — LobeHub cloud-sandbox / Manus computer use on LCA sandbox."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_MOUNT_ROOT,
    SandboxExecResult,
    SandboxFile,
)
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.computer.constants import COMPUTER_WORKSPACE_ROOT
from lca.layer0_infra.computer.guest import (
    build_edit_file_script,
    build_glob_files_script,
    build_grep_content_script,
    build_list_files_script,
    build_move_files_script,
    build_read_file_script,
    build_search_files_script,
    build_write_file_script,
)
from lca.layer0_infra.computer.parse_result import parse_computer_stdout
from lca.layer0_infra.file_store import FileStore
from lca.layer0_infra.sandbox.runtime_scope import ensure_sandbox_runtime
from lca.layer0_infra.tools.run_attachment_scope import get_current_run_attachment_ids
from lca.layer0_infra.tools.tool_invocation_scope import get_current_tool_invocation_id


@runtime_checkable
class TerminalCapableSandbox(Sandbox, Protocol):
    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> Any: ...


@dataclass(frozen=True)
class ComputerOpResult:
    success: bool
    content: str
    state: dict[str, Any]
    error: str = ""
    exec_result: SandboxExecResult | None = None
    generated_files: tuple[SandboxFile, ...] = ()


class _ComputerRuntimeBase:
    """Run-bound computer use plane — mirrors LobeHub CloudSandboxExecutionRuntime."""

    def __init__(self, *, sandbox: Sandbox, store: FileStore) -> None:
        self._sandbox = sandbox
        self._store = store

    async def _guest_op(
        self,
        script: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        invocation_id: str = "",
    ) -> ComputerOpResult:
        runtime = await ensure_sandbox_runtime(
            self._sandbox,
            self._store,
            attachment_ids=get_current_run_attachment_ids(),
        )
        inv = invocation_id or get_current_tool_invocation_id() or "computer"
        exec_result = await runtime.execute(
            script,
            language="python",
            timeout_s=timeout_s,
            invocation_id=inv,
            harvest_artifacts=False,
        )
        payload = parse_computer_stdout(exec_result.stdout)
        if payload is None:
            err = exec_result.error_summary or exec_result.error or "computer op parse failed"
            return ComputerOpResult(
                success=False,
                content=err,
                state={"success": False, "error": err},
                error=err,
                exec_result=exec_result,
            )
        ok = bool(payload.get("success", True))
        err = str(payload.get("error") or "")
        content = _format_content(payload)
        return ComputerOpResult(
            success=ok,
            content=content,
            state=payload,
            error=err,
            exec_result=exec_result,
        )

    async def list_files(self, *, directory_path: str) -> ComputerOpResult:
        path = _normalize_path(directory_path)
        return await self._guest_op(build_list_files_script(directory_path=path))

    async def read_file(
        self,
        *,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ComputerOpResult:
        return await self._guest_op(
            build_read_file_script(
                path=_normalize_path(path),
                start_line=start_line,
                end_line=end_line,
            )
        )

    async def write_file(
        self,
        *,
        path: str,
        content: str,
        create_directories: bool = True,
    ) -> ComputerOpResult:
        return await self._guest_op(
            build_write_file_script(
                path=_normalize_path(path),
                content=content,
                create_directories=create_directories,
            )
        )

    async def edit_file(
        self,
        *,
        path: str,
        search: str,
        replace: str,
        replace_all: bool = False,
    ) -> ComputerOpResult:
        return await self._guest_op(
            build_edit_file_script(
                path=_normalize_path(path),
                search=search,
                replace=replace,
                replace_all=replace_all,
            )
        )

    async def search_files(
        self,
        *,
        directory: str,
        keyword: str = "",
        file_type: str = "",
        modified_after: str = "",
        modified_before: str = "",
    ) -> ComputerOpResult:
        return await self._guest_op(
            build_search_files_script(
                directory=_normalize_path(directory),
                keyword=keyword,
                file_type=file_type,
                modified_after=modified_after,
                modified_before=modified_before,
            )
        )

    async def move_files(self, *, operations: list[dict[str, str]]) -> ComputerOpResult:
        normalized = [
            {
                "source": _normalize_path(op.get("source", "")),
                "destination": _normalize_path(op.get("destination", "")),
            }
            for op in operations
        ]
        return await self._guest_op(build_move_files_script(operations=normalized))

    async def grep_content(
        self,
        *,
        pattern: str,
        directory: str,
        file_pattern: str = "",
        recursive: bool = True,
    ) -> ComputerOpResult:
        return await self._guest_op(
            build_grep_content_script(
                pattern=pattern,
                directory=_normalize_path(directory),
                file_pattern=file_pattern,
                recursive=recursive,
            )
        )

    async def glob_files(self, *, pattern: str, directory: str = "") -> ComputerOpResult:
        return await self._guest_op(
            build_glob_files_script(
                pattern=pattern,
                directory=_normalize_path(directory) if directory else COMPUTER_WORKSPACE_ROOT,
            )
        )


def _normalize_path(path: str) -> str:
    cleaned = (path or "").strip()
    if not cleaned or cleaned in {".", "./"}:
        return COMPUTER_WORKSPACE_ROOT
    if cleaned.startswith("./"):
        return f"{SANDBOX_MOUNT_ROOT}/{cleaned[2:]}"
    return cleaned


def _format_content(payload: dict[str, Any]) -> str:
    if "content" in payload and isinstance(payload["content"], str):
        return payload["content"]
    if "output" in payload and isinstance(payload["output"], str):
        return payload["output"]
    if "files" in payload:
        return json.dumps(payload.get("files"), ensure_ascii=False)
    if "results" in payload:
        return json.dumps(payload.get("results"), ensure_ascii=False)
    if "matches" in payload:
        return json.dumps(payload.get("matches"), ensure_ascii=False)
    return json.dumps(payload, ensure_ascii=False)


from lca.layer0_infra.computer.runtime_exec import ComputerRuntimeExecMixin  # noqa: E402


class ComputerRuntime(_ComputerRuntimeBase, ComputerRuntimeExecMixin):
    """Run-bound computer use plane — mirrors LobeHub CloudSandboxExecutionRuntime."""
