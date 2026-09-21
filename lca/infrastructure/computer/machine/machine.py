"""MachineComputer — sidecar/SSH transport. Never holds a Sandbox."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from lca.contracts.models.core.execution.local_exec import (
    AccessScope,
    AccessVerdict,
)
from lca.contracts.models.core.state.plane import PlaneRef
from lca.contracts.protocols.runtime.infra.infra import MachineTransport
from lca.infrastructure.computer.machine.exec import MachineExecMixin
from lca.infrastructure.computer.op.result import ComputerOpResult
from lca.infrastructure.file.store import FileStore
from lca.infrastructure.runtime_plane.access.grant import default_access_scope
from lca.infrastructure.runtime_plane.access.policy import decide_access
from lca.infrastructure.runtime_plane.paths.paths import resolve_plane_path


class MachineComputer(MachineExecMixin):
    """File/shell/search/code on a machine PlaneRef. No export_file."""

    def __init__(
        self,
        plane: PlaneRef,
        transport: MachineTransport,
        store: FileStore,
        *,
        scope: AccessScope | None = None,
    ) -> None:
        self.plane = plane
        self._transport = transport
        self._store = store
        self._output_fingerprints: dict[str, str] = {}
        #: Run-scoped authorization facts. ``None`` falls back to the default
        #: shape derived from the plane alone (working root + home readable).
        self._scope = scope or default_access_scope(plane, "")

    def _gate(
        self, operation: str, paths: Sequence[str], *, command: str = ""
    ) -> tuple[list[str], ComputerOpResult | None]:
        """One authorization point for every operation.

        Returns ``(resolved_paths, None)`` when allowed, and
        ``([], denial_result)`` otherwise. A denial is a typed
        ``ComputerOpResult`` whose ``state`` carries ``error_kind`` and the
        ``AccessDecision`` as data, never an escaping exception, so a caller
        can route it to a consent pause or an effect receipt.
        """
        decision = decide_access(
            operation,
            scope=self._scope,
            plane=self.plane,
            paths=paths,
            command=command,
        )
        if decision.verdict is AccessVerdict.ALLOW:
            return [resolve_plane_path(p, self.plane) for p in paths], None
        if decision.verdict is AccessVerdict.DENY:
            message = f"scope_violation: {decision.detail or decision.reason.value}"
            return [], ComputerOpResult(
                success=False,
                content=message,
                state={
                    "success": False,
                    "error": message,
                    "error_kind": "scope_violation",
                    "verdict": decision.verdict.value,
                    "reason": decision.reason.value,
                    "retryable": False,
                    "plane": _plane_state(self.plane),
                },
                error=message,
            )
        message = f"approval_required: {decision.detail or decision.reason.value}"
        return [], ComputerOpResult(
            success=False,
            content=message,
            state={
                "success": False,
                "error": message,
                "error_kind": "approval_required",
                "verdict": decision.verdict.value,
                "reason": decision.reason.value,
                "retryable": False,
                "approval_request": {
                    "type": "path_scope",
                    "operation": decision.operation,
                    "verdict": decision.verdict.value,
                    "reason": decision.reason.value,
                    "path": decision.path,
                    "detail": decision.detail,
                },
                "plane": _plane_state(self.plane),
            },
            error=message,
        )

    async def list_files(self, *, directory_path: str) -> ComputerOpResult:
        paths, denied = self._gate("list_files", [directory_path or self.plane.root])
        if denied is not None:
            return denied
        return await self._op("listFiles", {"directory_path": paths[0]})

    async def read_file(
        self,
        *,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ComputerOpResult:
        paths, denied = self._gate("read_file", [path or self.plane.root])
        if denied is not None:
            return denied
        return await self._op(
            "readFile",
            {"path": paths[0], "start_line": start_line, "end_line": end_line},
        )

    async def write_file(
        self,
        *,
        path: str,
        content: str,
        create_directories: bool = True,
    ) -> ComputerOpResult:
        paths, denied = self._gate("write_file", [path])
        if denied is not None:
            return denied
        result = await self._op(
            "writeFile",
            {
                "path": paths[0],
                "content": content,
                "create_directories": create_directories,
            },
        )
        return await self._with_outputs(result, extra_path=paths[0], tool_name="writeFile")

    async def edit_file(
        self,
        *,
        path: str,
        search: str,
        replace: str,
        replace_all: bool = False,
    ) -> ComputerOpResult:
        paths, denied = self._gate("edit_file", [path])
        if denied is not None:
            return denied
        return await self._op(
            "editFile",
            {
                "path": paths[0],
                "search": search,
                "replace": replace,
                "replace_all": replace_all,
            },
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
        paths, denied = self._gate("search_files", [directory or self.plane.root])
        if denied is not None:
            return denied
        return await self._op(
            "searchFiles",
            {
                "directory": paths[0],
                "keyword": keyword,
                "file_type": file_type,
                "modified_after": modified_after,
                "modified_before": modified_before,
            },
        )

    async def move_files(self, *, operations: list[dict[str, str]]) -> ComputerOpResult:
        normalized: list[dict[str, str]] = [
            {
                "source": resolve_plane_path(item.get("source", ""), self.plane),
                "destination": resolve_plane_path(item.get("destination", ""), self.plane),
            }
            for item in operations
        ]
        endpoints = [path for pair in normalized for path in (pair["source"], pair["destination"])]
        _, denied = self._gate("move_files", endpoints)
        if denied is not None:
            return denied
        return await self._op("moveFiles", {"operations": normalized})

    async def grep_content(
        self,
        *,
        pattern: str,
        directory: str,
        file_pattern: str = "",
        recursive: bool = True,
    ) -> ComputerOpResult:
        paths, denied = self._gate("grep_content", [directory or self.plane.root])
        if denied is not None:
            return denied
        return await self._op(
            "grepContent",
            {
                "pattern": pattern,
                "directory": paths[0],
                "file_pattern": file_pattern,
                "recursive": recursive,
            },
        )

    async def glob_files(self, *, pattern: str, directory: str = "") -> ComputerOpResult:
        paths, denied = self._gate("glob_files", [directory or self.plane.root])
        if denied is not None:
            return denied
        return await self._op("globFiles", {"pattern": pattern, "directory": paths[0]})

    async def run_command(
        self,
        *,
        command: str,
        description: str = "",
        background: bool = False,
        timeout_s: int = 60,
    ) -> ComputerOpResult:
        del description
        _, denied = self._gate("run_command", (), command=command)
        if denied is not None:
            return denied
        result = await self._op(
            "runCommand",
            {
                "command": command,
                "cwd": self.plane.root,
                "background": background,
                "timeout_s": timeout_s,
                "timeout": timeout_s,
            },
            timeout_s=timeout_s,
        )
        return await self._with_outputs(result, tool_name="runCommand", command=command)

    async def get_command_output(self, *, command_id: str, timeout_s: int = 60) -> ComputerOpResult:
        return await self._op(
            "getCommandOutput",
            {"command_id": command_id},
            timeout_s=timeout_s,
        )

    async def kill_command(self, *, command_id: str) -> ComputerOpResult:
        return await self._op("killCommand", {"command_id": command_id})

    async def _with_outputs(
        self,
        result: ComputerOpResult,
        *,
        extra_path: str = "",
        tool_name: str = "",
        command: str = "",
    ) -> ComputerOpResult:
        from lca.infrastructure.computer.machine.harvest import attach_harvested_outputs

        return await attach_harvested_outputs(
            result,
            computer_op=self._transport.computer_op,
            plane=self.plane,
            store=self._store,
            seen=self._output_fingerprints,
            extra_path=extra_path,
            tool_name=tool_name,
            command=command,
        )

    async def _op(self, op: str, args: dict[str, Any], *, timeout_s: int = 60) -> ComputerOpResult:
        try:
            body = await self._transport.computer_op(op, args, timeout_s=timeout_s)
        except ConnectionError as exc:
            label = self.plane.label or self.plane.id
            err = f"device_offline: {label}: {exc}"
            return ComputerOpResult(
                success=False,
                content=err,
                state={
                    "success": False,
                    "error": err,
                    "retryable": True,
                    "error_kind": "device_offline",
                    "plane": _plane_state(self.plane),
                },
                error=err,
            )
        if not isinstance(body, dict):
            body = {"success": False, "error": "invalid local result"}
        ok = bool(body.get("success", False))
        err = str(body.get("error") or "")
        content = body.get("content")
        if not isinstance(content, str):
            content = _format(body) if ok or body.get("content") else err
        body.setdefault("plane", _plane_state(self.plane))
        # ADR-0102: normalise the on-guest camelCase renderer keys to the
        # snake_case python keys the RenderContracts declare.
        from lca.infrastructure.computer.runtime.exec import _normalize_guest_state

        _normalize_guest_state(body, tool_name=op)
        return ComputerOpResult(success=ok, content=content, state=body, error=err)


def _plane_state(plane: PlaneRef) -> dict[str, str]:
    return {
        "kind": plane.kind.value,
        "id": plane.id,
        "root": plane.root,
        "label": plane.label,
    }


def _format(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("content"), str):
        return str(payload["content"])
    if isinstance(payload.get("output"), str):
        return str(payload["output"])
    if "files" in payload:
        return json.dumps(payload.get("files"), ensure_ascii=False)
    return json.dumps(payload, ensure_ascii=False)
