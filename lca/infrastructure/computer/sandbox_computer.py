"""SandboxComputer — guest-script ops on an isolated sandbox PlaneRef."""

from __future__ import annotations

import json
from typing import Any

from lca.contracts.models.core.plane import PlaneRef
from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
)
from lca.contracts.protocols import Sandbox
from lca.infrastructure.computer.guest import (
    build_edit_file_script,
    build_glob_files_script,
    build_grep_content_script,
    build_list_files_script,
    build_move_files_script,
    build_read_file_script,
    build_search_files_script,
    build_write_file_script,
)
from lca.infrastructure.computer.op_result import ComputerOpResult
from lca.infrastructure.computer.parse_result import parse_computer_stdout
from lca.infrastructure.file_store import FileStore
from lca.infrastructure.sandbox.runtime_scope import ensure_sandbox_runtime
from lca.infrastructure.tools.tool_invocation_scope import get_current_tool_invocation_id


class _SandboxComputerBase:
    """File/shell/search via guest Python inside a sandbox plane."""

    def __init__(
        self,
        *,
        plane: PlaneRef,
        sandbox: Sandbox,
        store: FileStore,
    ) -> None:
        self.plane = plane
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
            attachment_ids=_get_current_run_attachment_ids(),
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
        # ADR-0102: normalise the on-guest camelCase renderer keys to the
        # snake_case python keys the RenderContracts declare.
        from lca.infrastructure.computer.runtime_exec import _normalize_guest_state

        _normalize_guest_state(payload, tool_name=invocation_id)
        return ComputerOpResult(
            success=ok,
            content=content,
            state=payload,
            error=err,
            exec_result=exec_result,
        )

    async def list_files(self, *, directory_path: str) -> ComputerOpResult:
        path = normalize_sandbox_path(directory_path, self.plane.root)
        return await self._guest_op(build_list_files_script(directory_path=path))

    async def read_file(
        self,
        *,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ComputerOpResult:
        norm = normalize_sandbox_path(path, self.plane.root)
        return await self._guest_op(
            build_read_file_script(path=norm, start_line=start_line, end_line=end_line)
        )

    async def write_file(
        self,
        *,
        path: str,
        content: str,
        create_directories: bool = True,
    ) -> ComputerOpResult:
        norm = normalize_sandbox_path(path, self.plane.root)
        return await self._guest_op(
            build_write_file_script(
                path=norm, content=content, create_directories=create_directories
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
        norm = normalize_sandbox_path(path, self.plane.root)
        return await self._guest_op(
            build_edit_file_script(
                path=norm, search=search, replace=replace, replace_all=replace_all
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
        norm = normalize_sandbox_path(directory, self.plane.root)
        return await self._guest_op(
            build_search_files_script(
                directory=norm,
                keyword=keyword,
                file_type=file_type,
                modified_after=modified_after,
                modified_before=modified_before,
            )
        )

    async def move_files(self, *, operations: list[dict[str, str]]) -> ComputerOpResult:
        normalized = [
            {
                "source": normalize_sandbox_path(op.get("source", ""), self.plane.root),
                "destination": normalize_sandbox_path(op.get("destination", ""), self.plane.root),
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
        norm = normalize_sandbox_path(directory, self.plane.root)
        return await self._guest_op(
            build_grep_content_script(
                pattern=pattern,
                directory=norm,
                file_pattern=file_pattern,
                recursive=recursive,
            )
        )

    async def glob_files(self, *, pattern: str, directory: str = "") -> ComputerOpResult:
        norm = normalize_sandbox_path(directory, self.plane.root) if directory else self.plane.root
        return await self._guest_op(build_glob_files_script(pattern=pattern, directory=norm))


def normalize_sandbox_path(path: str, root: str) -> str:
    """Relative paths resolve against the sandbox plane root. No cross-plane remap."""
    cleaned = (path or "").strip()
    if not cleaned or cleaned in {".", "./"}:
        return root
    if cleaned.startswith("./"):
        return f"{root.rstrip('/')}/{cleaned[2:]}"
    if cleaned.startswith("/"):
        return cleaned
    return f"{root.rstrip('/')}/{cleaned}"


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


from lca.infrastructure.computer.runtime_exec import ComputerRuntimeExecMixin  # noqa: E402


class SandboxComputer(_SandboxComputerBase, ComputerRuntimeExecMixin):
    """Isolated sandbox adapter — mirrors LobeHub CloudSandboxExecutionRuntime."""


__all__ = ["SandboxComputer", "normalize_sandbox_path"]


def _get_current_run_attachment_ids() -> tuple[str, ...]:
    """Lazy import to break circular import (sandbox_computer ↔ tools)."""
    from lca.infrastructure.tools.run_attachment_scope import get_current_run_attachment_ids
    return get_current_run_attachment_ids()
