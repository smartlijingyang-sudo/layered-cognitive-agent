"""MachineComputer — sidecar/SSH transport. Never holds a Sandbox."""

from __future__ import annotations

import json
from typing import Any, Protocol

from lca.contracts.models.core.plane import PlaneRef
from lca.layer0_infra.computer.machine_exec import MachineExecMixin
from lca.layer0_infra.computer.op_result import ComputerOpResult
from lca.layer0_infra.file_store import FileStore, get_default_file_store
from lca.layer0_infra.plane.scope import raise_if_out_of_scope


class MachineTransport(Protocol):
    """Machine plane 传输——系统通道。

    ``write_files`` 的所有调用方都是受信的基础设施操作（附件暂存），
    等价于 ``Sandbox.write_files()``——Protocol 本身就是信任边界。
    用户写入走 ``MachineComputer.write_file()`` tool call（CLI ``writeFile``
    单数），有独立的 ``assertWritable`` 策略。
    """

    async def computer_op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> dict[str, Any]: ...

    async def write_files(
        self,
        files: dict[str, bytes | str],
        *,
        base_dir: str = "",
        session_id: str = "",
        timeout_s: int = 60,
    ) -> Any: ...


class MachineComputer(MachineExecMixin):
    """File/shell/search/code on a machine PlaneRef. No export_file."""

    def __init__(
        self,
        plane: PlaneRef,
        transport: MachineTransport,
        store: FileStore | None = None,
    ) -> None:
        self.plane = plane
        self._transport = transport
        self._store = store if store is not None else get_default_file_store()

    async def list_files(self, *, directory_path: str) -> ComputerOpResult:
        path = raise_if_out_of_scope(directory_path or self.plane.root, self.plane)
        return await self._op("listFiles", {"directory_path": path})

    async def read_file(
        self,
        *,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ComputerOpResult:
        resolved = raise_if_out_of_scope(path or self.plane.root, self.plane)
        return await self._op(
            "readFile",
            {"path": resolved, "start_line": start_line, "end_line": end_line},
        )

    async def write_file(
        self,
        *,
        path: str,
        content: str,
        create_directories: bool = True,
    ) -> ComputerOpResult:
        resolved = raise_if_out_of_scope(path, self.plane)
        result = await self._op(
            "writeFile",
            {
                "path": resolved,
                "content": content,
                "create_directories": create_directories,
            },
        )
        await self._publish_outputs(result, extra_path=resolved)
        return result

    async def edit_file(
        self,
        *,
        path: str,
        search: str,
        replace: str,
        replace_all: bool = False,
    ) -> ComputerOpResult:
        resolved = raise_if_out_of_scope(path, self.plane)
        return await self._op(
            "editFile",
            {
                "path": resolved,
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
        resolved = raise_if_out_of_scope(directory or self.plane.root, self.plane)
        return await self._op(
            "searchFiles",
            {
                "directory": resolved,
                "keyword": keyword,
                "file_type": file_type,
                "modified_after": modified_after,
                "modified_before": modified_before,
            },
        )

    async def move_files(self, *, operations: list[dict[str, str]]) -> ComputerOpResult:
        normalized: list[dict[str, str]] = []
        for item in operations:
            normalized.append(
                {
                    "source": raise_if_out_of_scope(item.get("source", ""), self.plane),
                    "destination": raise_if_out_of_scope(item.get("destination", ""), self.plane),
                }
            )
        return await self._op("moveFiles", {"operations": normalized})

    async def grep_content(
        self,
        *,
        pattern: str,
        directory: str,
        file_pattern: str = "",
        recursive: bool = True,
    ) -> ComputerOpResult:
        resolved = raise_if_out_of_scope(directory or self.plane.root, self.plane)
        return await self._op(
            "grepContent",
            {
                "pattern": pattern,
                "directory": resolved,
                "file_pattern": file_pattern,
                "recursive": recursive,
            },
        )

    async def glob_files(self, *, pattern: str, directory: str = "") -> ComputerOpResult:
        resolved = raise_if_out_of_scope(directory or self.plane.root, self.plane)
        return await self._op("globFiles", {"pattern": pattern, "directory": resolved})

    async def run_command(
        self,
        *,
        command: str,
        description: str = "",
        background: bool = False,
        timeout_s: int = 60,
    ) -> ComputerOpResult:
        del description
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
        await self._publish_outputs(result)
        return result

    async def get_command_output(self, *, command_id: str, timeout_s: int = 60) -> ComputerOpResult:
        return await self._op(
            "getCommandOutput",
            {"command_id": command_id},
            timeout_s=timeout_s,
        )

    async def kill_command(self, *, command_id: str) -> ComputerOpResult:
        return await self._op("killCommand", {"command_id": command_id})

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
