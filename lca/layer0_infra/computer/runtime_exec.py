"""ComputerRuntime execution plane — code, shell, background, export."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, Protocol

import structlog

from lca.contracts.models.core.sandbox import DEFAULT_SANDBOX_TIMEOUT_S, SandboxFile
from lca.contracts.models.core.sandbox_policy import SandboxPolicy
from lca.layer0_infra.computer.background import get_background_registry
from lca.layer0_infra.computer.cli_json import cli_json_success
from lca.layer0_infra.computer.guest import (
    build_background_kill_script,
    build_background_poll_script,
    build_background_start_script,
    build_read_bytes_script,
    build_shell_script,
)
from lca.layer0_infra.computer.office_plane import normalize_officecli_command
from lca.layer0_infra.computer.op_result import ComputerOpResult, TerminalCapableSandbox
from lca.layer0_infra.computer.sandbox_computer import normalize_sandbox_path
from lca.layer0_infra.file_store import FileStore, get_default_file_store, persist_generated_files
from lca.layer0_infra.sandbox.factory import get_sandbox_policy
from lca.layer0_infra.sandbox.runtime_scope import ensure_sandbox_runtime
from lca.layer0_infra.tools.run_attachment_scope import get_current_run_attachment_ids
from lca.layer0_infra.tools.tool_invocation_scope import get_current_tool_invocation_id
from lca.layer0_infra.workspace.deliverable import (
    is_office_name,
    is_office_publish_intent,
    visible_generated_files,
)

_log = structlog.get_logger(__name__)


def _store_generated_file_parts(
    store: FileStore,
    files: Sequence[SandboxFile],
) -> list[dict[str, Any]]:
    """Persist harvested sandbox files once; canonical file-part shape."""
    try:
        return persist_generated_files(store, files)
    except Exception:
        _log.warning("auto_store_generated_file_failed", exc_info=True)
        return []


def _check_writable(path: str, policy: SandboxPolicy) -> None:
    """Warn or raise if *path* is outside writable_roots or inside denied_write_roots."""
    resolved = os.path.realpath(path)
    for root in policy.writable_roots:
        root_resolved = os.path.realpath(root)
        if resolved == root_resolved or resolved.startswith(root_resolved + os.sep):
            if policy.denied_write_roots:
                for denied in policy.denied_write_roots:
                    denied_resolved = os.path.realpath(denied)
                    if resolved == denied_resolved or resolved.startswith(denied_resolved + os.sep):
                        _log.warning("sandbox_policy_denied_write", path=path, denied=denied)
                        if policy.on_unavailable == "error":
                            raise PermissionError(
                                f"write denied: {path} is in denied root {denied}"
                            )
            return
    if policy.on_unavailable == "error":
        raise PermissionError(
            f"write denied: {path} is outside writable roots {list(policy.writable_roots)}"
        )
    _log.warning(
        "sandbox_policy_outside_writable",
        path=path,
        writable_roots=list(policy.writable_roots),
    )


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
        inv = get_current_tool_invocation_id() or "executeCode"

        # Artifact collection is embedded in the bootstrap template at the
        # same indentation level as user code — no wrapping needed.
        exec_result = await runtime.execute(
            code,
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

        # Auto-store generated files so they have download URLs immediately.
        # This eliminates the need for a separate export_file call — files
        # produced in the sandbox are always accessible to the frontend.
        file_parts = _store_generated_file_parts(
            get_default_file_store(),
            visible_generated_files(exec_result.generated_files, tool_name="executeCode"),
        )
        if file_parts:
            state["files"] = file_parts

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
        inv = get_current_tool_invocation_id() or "runCommand"
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
            command = normalize_officecli_command(command)
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
            json_ok = cli_json_success(terminal_result.stdout)
            ok = terminal_result.success if json_ok is None else json_ok
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
                state["error"] = terminal_result.error or (
                    f"exit_code={terminal_result.exit_code}" if terminal_result.exit_code else ""
                )
            generated = terminal_result.generated_files
            if is_office_publish_intent(tool_name="runCommand", command=command):
                scanned = await runtime.scan_output_files(invocation_id=f"{inv}_office_pub")
                generated = tuple(generated) + tuple(
                    item for item in scanned if is_office_name(item.name)
                )
            file_parts = _store_generated_file_parts(
                get_default_file_store(),
                visible_generated_files(generated, tool_name="runCommand", command=command),
            )
            if file_parts:
                state["files"] = file_parts
            content = terminal_result.stdout or terminal_result.stderr or command
            return ComputerOpResult(
                success=ok,
                content=content,
                state=state,
                error="" if ok else (state.get("error") or terminal_result.error),
                generated_files=generated,
            )

        guest = await self._guest_op(
            build_shell_script(command=command),
            timeout_s=timeout_s,
            invocation_id=inv,
        )
        guest.state.setdefault("command", command)
        guest.state.setdefault("executionEnv", "sandbox")
        guest.state.setdefault("isBackground", False)
        # Guest shell path uses execute() + artifact scanner; surface files.
        if guest.exec_result is not None and guest.exec_result.generated_files:
            generated = guest.exec_result.generated_files
            file_parts = _store_generated_file_parts(
                get_default_file_store(),
                visible_generated_files(generated, tool_name="runCommand", command=command),
            )
            if file_parts:
                guest.state["files"] = file_parts
            return ComputerOpResult(
                success=guest.success,
                content=guest.content,
                state=guest.state,
                error=guest.error,
                exec_result=guest.exec_result,
                generated_files=generated,
            )
        return guest

    async def get_command_output(self: _GuestOpHost, *, command_id: str) -> ComputerOpResult:
        return await self._guest_op(build_background_poll_script(command_id=command_id))

    async def kill_command(self: _GuestOpHost, *, command_id: str) -> ComputerOpResult:
        result = await self._guest_op(build_background_kill_script(command_id=command_id))
        if result.success:
            get_background_registry().mark_stopped(command_id)
        return result

    async def export_file(self: _GuestOpHost, *, path: str) -> ComputerOpResult:
        import base64

        _check_writable(path, get_sandbox_policy())
        normalized = normalize_sandbox_path(path, self.plane.root)
        read = await self._guest_op(build_read_bytes_script(path=normalized))
        if not read.success:
            return read
        b64_raw = read.state.get("b64")
        if not isinstance(b64_raw, str) or not b64_raw:
            err = str(read.state.get("error") or "export read failed")
            return ComputerOpResult(
                success=False,
                content=err,
                state={"success": False, "error": err, "path": normalized},
                error=err,
            )
        data = base64.b64decode(b64_raw)
        filename = str(read.state.get("filename") or normalized.rsplit("/", 1)[-1] or "export.bin")
        mime_type = str(read.state.get("mimeType") or "application/octet-stream")
        stored = self._store.put(data=data, name=filename, mime_type=mime_type)
        state = {
            "success": True,
            "path": normalized,
            "filename": stored.name,
            "downloadUrl": stored.url,
            "mimeType": mime_type,
            "size": stored.size_bytes,
        }
        sandbox_file = SandboxFile(name=filename, mime_type=mime_type, data=data)
        return ComputerOpResult(
            success=True,
            content=f"Exported {filename} ({stored.size_bytes} bytes)",
            state=state,
            generated_files=(sandbox_file,),
        )
