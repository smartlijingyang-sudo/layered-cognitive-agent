"""Machine execute_code + output harvest — keep machine.py under line budget."""

from __future__ import annotations

import hashlib
import os
import time
from typing import Any, Protocol

from lca.layer0_infra.computer.op_result import ComputerOpResult
from lca.layer0_infra.file_store import FileStore

_LANGUAGE_EXT: dict[str, str] = {
    "python": "py",
    "python3": "py",
    "javascript": "js",
    "typescript": "ts",
}
_LANGUAGE_INTERPRETER: dict[str, str] = {
    "python": "python3",
    "python3": "python3",
    "javascript": "node",
    "typescript": "npx ts-node",
}


class _MachineOp(Protocol):
    plane: Any
    _store: FileStore

    async def _op(
        self, op: str, args: dict[str, Any], *, timeout_s: int = 60
    ) -> ComputerOpResult: ...


class MachineExecMixin:
    """Temp-file code execution on a machine plane."""

    async def execute_code(
        self: _MachineOp,
        *,
        code: str,
        language: str = "python",
        description: str = "",
        timeout_s: int = 60,
    ) -> ComputerOpResult:
        """Write a temp script, run it, then delete it.

        Avoids the two-step writeFile + runCommand loop and keeps encoding
        at the transport boundary.
        """
        del description
        nonce = hashlib.sha256(f"{code}:{time.monotonic()}".encode()).hexdigest()[:12]
        ext = _LANGUAGE_EXT.get(language.lower(), "py")
        temp_path = f"{self.plane.root}/.lca/exec_{nonce}.{ext}"

        write_result = await self._op(
            "writeFile",
            {"path": temp_path, "content": code, "create_directories": True},
        )
        if not write_result.success:
            return ComputerOpResult(
                success=False,
                content="",
                state={"error": f"write temp file failed: {write_result.error}"},
                error=write_result.error or "write temp file failed",
            )

        interpreter = _LANGUAGE_INTERPRETER.get(language.lower(), "python3")
        exec_result = await self._op(
            "runCommand",
            {
                "command": f"{interpreter} {temp_path}",
                "cwd": self.plane.root,
                "background": False,
                "timeout_s": timeout_s,
                "timeout": timeout_s,
            },
            timeout_s=timeout_s,
        )
        await self._op("runCommand", {"command": f"rm -f {temp_path}", "cwd": self.plane.root})
        if not exec_result.success:
            return ComputerOpResult(
                success=False,
                content=exec_result.content,
                state={**exec_result.state, "language": language, "temp_path": temp_path},
                error=exec_result.error or exec_result.content or "code execution failed",
            )
        return exec_result

    async def _publish_outputs(
        self: _MachineOp, result: ComputerOpResult, *, extra_path: str = ""
    ) -> None:
        if not result.success:
            return
        paths: list[str] = []
        outputs_dir = self.plane.outputs_dir
        if extra_path and _under_dir(extra_path, outputs_dir):
            paths.append(extra_path)
        listed = await self._op("listFiles", {"directory_path": outputs_dir})
        for item in listed.state.get("files") or []:
            if not isinstance(item, dict):
                continue
            candidate = str(item.get("path") or item.get("name") or "")
            if not candidate:
                continue
            resolved = candidate if candidate.startswith("/") else f"{outputs_dir}/{candidate}"
            if not _under_dir(resolved, outputs_dir):
                continue
            paths.append(
                candidate
                if candidate.startswith(outputs_dir)
                else f"{outputs_dir.rstrip('/')}/{candidate}"
            )
        published: list[dict[str, str]] = []
        for path in dict.fromkeys(paths):
            read = await self._op("readFile", {"path": path})
            raw = read.state.get("content")
            if not isinstance(raw, str) or not raw:
                result.state["publish_error"] = f"could not read {path} for download"
                continue
            name = path.replace("\\", "/").rsplit("/", 1)[-1]
            stored = self._store.put(
                data=raw.encode("utf-8"),
                name=name,
                mime_type="application/octet-stream",
            )
            published.append({"filename": name, "url": f"/files/{stored.attachment_id}"})
        if published:
            result.state.setdefault("files", [])
            if isinstance(result.state["files"], list):
                result.state["files"].extend(published)


def _under_dir(path: str, directory: str) -> bool:
    left = os.path.normpath(path)
    right = os.path.normpath(directory)
    return left == right or left.startswith(right + os.sep)
