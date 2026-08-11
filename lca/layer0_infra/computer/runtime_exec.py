"""ComputerRuntime execution plane — code, shell, background, export."""

from __future__ import annotations

import textwrap
from typing import Any, Protocol

from lca.contracts.models.core.sandbox import DEFAULT_SANDBOX_TIMEOUT_S
from lca.layer0_infra.computer.background import get_background_registry
from lca.layer0_infra.computer.guest import (
    build_background_kill_script,
    build_background_poll_script,
    build_background_start_script,
    build_shell_script,
)
from lca.layer0_infra.computer.runtime import (
    ComputerOpResult,
    TerminalCapableSandbox,
    _normalize_path,
)
from lca.layer0_infra.sandbox.runtime_scope import ensure_sandbox_runtime
from lca.layer0_infra.tools.run_attachment_scope import get_current_run_attachment_ids
from lca.layer0_infra.tools.tool_invocation_scope import get_current_tool_invocation_id

# ADR-0046 compliant: only scans /mnt/data/outputs/ (not /mnt/data/ root)
_ARTIFACT_SCANNER = """
import os as _os, json as _json, base64 as _b64, mimetypes as _mt
try:
    _scan_files = []
    _output_dir = "/mnt/data/outputs"
    if _os.path.isdir(_output_dir):
        for _fname in _os.listdir(_output_dir):
            _fpath = _os.path.join(_output_dir, _fname)
            if _os.path.isfile(_fpath):
                try:
                    with open(_fpath, "rb") as _fh:
                        _raw = _fh.read()
                    _scan_files.append({
                        "name": _fname,
                        "b64": _b64.b64encode(_raw).decode(),
                        "mime_type": _mt.guess_type(_fname)[0] or "application/octet-stream",
                    })
                except Exception:
                    pass
    if _scan_files:
        print("__LCA_ONLYBOXES_ARTIFACTS__" + _json.dumps(_scan_files) + "__END_LCA_ARTIFACTS__")
except Exception:
    pass
"""


class _GuestOpHost(Protocol):
    _sandbox: Any
    _store: Any

    async def _guest_op(
        self,
        script: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        invocation_id: str = "",
    ) -> ComputerOpResult: ...

    async def read_file(
        self,
        *,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ComputerOpResult: ...


class ComputerRuntimeExecMixin:
    """Mixin: execute_code, run_command, background command control, export."""

    async def execute_code(
        self: _GuestOpHost,
        *,
        code: str,
        language: str = "python",
        description: str = "",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
    ) -> ComputerOpResult:
        del description
        lang = (language or "python").lower()
        runtime = await ensure_sandbox_runtime(
            self._sandbox,
            self._store,
            attachment_ids=get_current_run_attachment_ids(),
        )
        inv = get_current_tool_invocation_id() or "execute_code"

        # Inject ADR-0046 compliant artifact scanner via try/finally
        wrapped_code = (
            "try:\n"
            + textwrap.indent(code, "    ")
            + "\nfinally:\n"
            + textwrap.indent(_ARTIFACT_SCANNER, "    ")
        )

        exec_result = await runtime.execute(
            wrapped_code,
            language=lang if lang in {"python", "py"} else "python",
            timeout_s=timeout_s,
            invocation_id=inv,
        )
        ok = exec_result.success
        state: dict[str, Any] = {
            "success": ok,
            "language": lang,
            "output": exec_result.stdout,
            "stderr": exec_result.stderr,
            "exitCode": exec_result.exit_code,
            "code": code,  # source code always visible in tool card
        }
        if not ok:
            state["error"] = exec_result.error_summary or exec_result.error
        content = (
            exec_result.stdout or exec_result.stderr or ("ok" if ok else state.get("error", ""))
        )
        return ComputerOpResult(
            success=ok,
            content=str(content),
            state=state,
            error=str(state.get("error") or ""),
            exec_result=exec_result,
            generated_files=exec_result.generated_files,
        )

    async def run_command(
        self: _GuestOpHost,
        *,
        command: str,
        description: str = "",
        background: bool = False,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
    ) -> ComputerOpResult:
        del description
        inv = get_current_tool_invocation_id() or "run_command"
        if background:
            registry = get_background_registry()
            command_id = registry.register(command=command)
            result = await self._guest_op(
                build_background_start_script(command=command, command_id=command_id),
                timeout_s=timeout_s,
                invocation_id=inv,
            )
            if result.success and "commandId" not in result.state:
                result.state["commandId"] = command_id
            return result

        if isinstance(self._sandbox, TerminalCapableSandbox):
            runtime = await ensure_sandbox_runtime(
                self._sandbox,
                self._store,
                attachment_ids=get_current_run_attachment_ids(),
            )
            await runtime.ensure_ready()
            terminal_result = await runtime.run_terminal(
                command,
                timeout_s=timeout_s,
                invocation_id=inv,
            )
            ok = terminal_result.success
            state: dict[str, Any] = {
                "success": ok,
                "command": command,
                "executionEnv": "sandbox",
                "stdout": terminal_result.stdout,
                "stderr": terminal_result.stderr,
                "output": terminal_result.stdout or terminal_result.stderr,
                "exitCode": terminal_result.exit_code,
                "isBackground": False,
            }
            if not ok:
                state["error"] = terminal_result.error
            content = terminal_result.stdout or terminal_result.stderr or command
            return ComputerOpResult(
                success=ok,
                content=content,
                state=state,
                error=terminal_result.error,
            )

        guest = await self._guest_op(
            build_shell_script(command=command),
            timeout_s=timeout_s,
            invocation_id=inv,
        )
        guest.state.setdefault("command", command)
        guest.state.setdefault("executionEnv", "sandbox")
        guest.state.setdefault("isBackground", False)
        return guest

    async def get_command_output(self: _GuestOpHost, *, command_id: str) -> ComputerOpResult:
        return await self._guest_op(build_background_poll_script(command_id=command_id))

    async def kill_command(self: _GuestOpHost, *, command_id: str) -> ComputerOpResult:
        result = await self._guest_op(build_background_kill_script(command_id=command_id))
        if result.success:
            get_background_registry().mark_stopped(command_id)
        return result

    async def export_file(self: _GuestOpHost, *, path: str) -> ComputerOpResult:
        read = await self.read_file(path=_normalize_path(path))
        if not read.success:
            return read
        content = str(read.state.get("content") or "")
        filename = str(read.state.get("filename") or path.rsplit("/", 1)[-1] or "export.bin")
        stored = self._store.put(
            data=content.encode("utf-8"),
            name=filename,
            mime_type="application/octet-stream",
        )
        state = {
            "success": True,
            "path": path,
            "filename": stored.name,
            "downloadUrl": stored.url,
            "size": stored.size_bytes,
        }
        return ComputerOpResult(
            success=True,
            content=f"Exported {filename} ({stored.size_bytes} bytes)",
            state=state,
        )
