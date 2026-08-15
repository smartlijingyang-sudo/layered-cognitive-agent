"""Machine execute_code + output harvest — keep machine.py under line budget."""

from __future__ import annotations

import hashlib
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
    _transport: Any
    _output_fingerprints: dict[str, str]

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
        """Write a temp script via the system channel, run it, then delete it.

        Sidecar ``writeFile`` denies ``.lca/`` (agent-facing). Temp scripts are
        infrastructure — same trust boundary as attachment staging.
        """
        del description
        from lca.layer0_infra.computer.machine_harvest import attach_harvested_outputs

        nonce = hashlib.sha256(f"{code}:{time.monotonic()}".encode()).hexdigest()[:12]
        ext = _LANGUAGE_EXT.get(language.lower(), "py")
        rel = f".lca/exec_{nonce}.{ext}"
        temp_path = f"{str(self.plane.root).rstrip('/')}/{rel}"

        written = await self._transport.write_files(
            {rel: code.encode("utf-8")},
            base_dir=self.plane.root,
        )
        if written is not None and getattr(written, "success", True) is False:
            err = str(getattr(written, "error", "") or "write temp file failed")
            return ComputerOpResult(
                success=False,
                content="",
                state={"error": f"write temp file failed: {err}"},
                error=err,
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
        return await attach_harvested_outputs(
            exec_result,
            computer_op=self._transport.computer_op,
            plane=self.plane,
            store=self._store,
            seen=self._output_fingerprints,
            tool_name="executeCode",
        )
