"""ComputerRuntime execution plane — code, shell, background, export."""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any, Protocol

import structlog

from lca.contracts.atoms.enums import SpanStatus
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
from lca.layer0_infra.file_store import FileStore, persist_generated_files
from lca.layer0_infra.sandbox.factory import get_sandbox_policy
from lca.layer0_infra.sandbox.runtime_scope import ensure_sandbox_runtime
from lca.layer0_infra.workspace.deliverable import (
    is_office_name,
    is_office_publish_intent,
    visible_generated_files,
)

# ── Guest → wire-shape normaliser ───────────────────────────────────
# ADR-0102: the on-guest SHELL/FILE scripts emit camelCase renderer
# keys (the legacy LobeHub wire shape).  The RenderContracts in
# ``lca.layer0_infra.tools.contract.sandbox_contracts`` declare snake_case
# python keys.  This helper bridges the two at the seam so downstream
# ``build_computer_observation`` does not need a second rename pass.
_GUEST_KEY_RENAMES: dict[str, str] = {
    "executionEnv": "execution_env",
    "exitCode": "exit_code",
    "errorKind": "error_kind",
    "errorSummary": "error_summary",
    "isBackground": "is_background",
    "totalCount": "total_count",
    "totalMatches": "total_matches",
    "successCount": "success_count",
    "directoryPath": "directory_path",
    "totalCharCount": "total_char_count",
    "totalLines": "total_lines",
    "charCount": "char_count",
    "startLine": "start_line",
    "endLine": "end_line",
    "fileType": "file_type",
    "mimeType": "mime_type",
    "bytesWritten": "bytes_written",
    "linesAdded": "lines_added",
    "linesDeleted": "lines_deleted",
    "filePattern": "file_pattern",
    "modifiedAfter": "modified_after",
    "modifiedBefore": "modified_before",
    "commandId": "command_id",
    "createDirectories": "create_directories",
    "replaceAll": "replace_all",
}


def _normalize_guest_state(state: dict[str, Any], *, tool_name: str = "") -> dict[str, Any]:
    """Rename legacy camelCase guest keys to snake_case python keys.

    ADR-0102: ``RenderContract.python_key`` is the SSOT.  The on-guest
    scripts still emit camelCase (they predate ADR-0102).  Normalise in
    place so downstream contracts can find what they expect.
    """
    if not isinstance(state, dict):
        return state
    for camel, snake in _GUEST_KEY_RENAMES.items():
        if camel in state and snake not in state:
            state[snake] = state.pop(camel)
    # ``output`` is a stdout/stderr alias the guest uses; drop it so the
    # contract's ``stdout`` field is the single source of truth.
    if "stdout" in state and "output" in state:
        state.pop("output", None)
    return state


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
                        if policy.on_unavailable == SpanStatus.ERROR:
                            raise PermissionError(
                                f"write denied: {path} is in denied root {denied}"
                            )
            return
    if policy.on_unavailable == SpanStatus.ERROR:
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
    plane: Any  # PlaneRef; relaxed to Any to keep the Protocol import-light

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
            attachment_ids=_re_get("attachment_ids"),
        )
        inv = _re_get("inv") or "executeCode"

        # Artifact collection is embedded in the bootstrap template at the
        # same indentation level as user code — no wrapping needed.
        exec_result = await runtime.execute(
            code,
            language=lang if lang in {"python", "py"} else "python",
            timeout_s=timeout_s,
            invocation_id=inv,
        )
        ok = exec_result.success
        # ADR-0102: state is the Tool's wire-shape view.  Emit snake_case
        # python keys matching the ``executeCode`` RenderContract (python_key
        # 'stdout' / 'stderr' / 'exit_code' / 'execution_env' /
        # 'error_summary' / 'error_kind').  Code stays in args; renderer
        # reads ``pluginState.stdout`` for output.
        state: dict[str, Any] = {
            "success": ok,
            "language": lang,
            "stdout": exec_result.stdout,
            "stderr": exec_result.stderr,
            "exit_code": exec_result.exit_code,
            "execution_env": "sandbox",
            "code": code,  # source code always visible in tool card
        }
        if not ok:
            state["error"] = exec_result.error_summary or exec_result.error
            state["error_summary"] = exec_result.error_summary or exec_result.error
            state["error_kind"] = exec_result.error_kind.value

        # Auto-store generated files so they have download URLs immediately.
        # This eliminates the need for a separate export_file call — files
        # produced in the sandbox are always accessible to the frontend.
        file_parts = _store_generated_file_parts(
            self._store,
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
        inv = _re_get("inv") or "runCommand"
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
                attachment_ids=_re_get("attachment_ids"),
            )
            await runtime.ensure_ready()
            terminal_result = await runtime.run_terminal(
                command,
                timeout_s=timeout_s,
                invocation_id=inv,
            )
            json_ok = cli_json_success(terminal_result.stdout)
            ok = terminal_result.success if json_ok is None else json_ok
            # ADR-0102: state is the Tool's wire-shape view.  Snake_case
            # python keys matching the ``runCommand`` RenderContract.  The
            # legacy ``output`` alias is dropped — renderer reads
            # ``pluginState.stdout`` directly.  ``error_summary`` /
            # ``error_kind`` surface ``SandboxExecResult`` annotations on
            # failure (renderer uses them for the failure card).
            state: dict[str, Any] = {
                "success": ok,
                "command": command,
                "execution_env": "sandbox",
                "stdout": terminal_result.stdout,
                "stderr": terminal_result.stderr,
                "exit_code": terminal_result.exit_code,
                "is_background": False,
            }
            if not ok:
                state["error"] = terminal_result.error or (
                    f"exit_code={terminal_result.exit_code}" if terminal_result.exit_code else ""
                )
                state["error_summary"] = terminal_result.error_summary or terminal_result.error
                state["error_kind"] = getattr(terminal_result.error_kind, 'value', None) or 'none'
            generated = terminal_result.generated_files
            if is_office_publish_intent(tool_name="runCommand", command=command):
                scanned = await runtime.scan_output_files(invocation_id=f"{inv}_office_pub")
                generated = tuple(generated) + tuple(
                    item for item in scanned if is_office_name(item.name)
                )
            file_parts = _store_generated_file_parts(
                self._store,
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
        # ADR-0102: snake_case python keys on the guest path too.  The guest
        # SHELL_SCRIPT still emits legacy camelCase; normalise here so
        # ``runCommand`` produces a uniform shape regardless of dispatch.
        _normalize_guest_state(guest.state, tool_name="runCommand")
        guest.state.setdefault("command", command)
        guest.state.setdefault("execution_env", "sandbox")
        guest.state.setdefault("is_background", False)
        # Guest shell path uses execute() + artifact scanner; surface files.
        if guest.exec_result is not None and guest.exec_result.generated_files:
            generated = guest.exec_result.generated_files
            file_parts = _store_generated_file_parts(
                self._store,
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

    async def get_command_output(
        self: _GuestOpHost, *, command_id: str, timeout_s: int = 60
    ) -> ComputerOpResult:
        guest = await self._guest_op(build_background_poll_script(command_id=command_id))
        _normalize_guest_state(guest.state, tool_name="getCommandOutput")
        # ``partial`` flag tells the renderer the background command is
        # still streaming.  Renderer card shows "still running".
        guest.state.setdefault("partial", bool(guest.state.get("running", False)))
        guest.state.setdefault("command_id", command_id)
        return guest

    async def kill_command(self: _GuestOpHost, *, command_id: str) -> ComputerOpResult:
        result = await self._guest_op(build_background_kill_script(command_id=command_id))
        _normalize_guest_state(result.state, tool_name="killCommand")
        result.state.setdefault("command_id", command_id)
        if result.success:
            result.state.setdefault("killed", True)
            get_background_registry().mark_stopped(command_id)
        return result

    async def export_file(self: _GuestOpHost, *, path: str) -> ComputerOpResult:
        import base64

        _check_writable(path, get_sandbox_policy())
        normalized = normalize_sandbox_path(path, self.plane.root)
        read = await self._guest_op(build_read_bytes_script(path=normalized))
        _normalize_guest_state(read.state, tool_name="exportFile")
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
        mime_type = str(read.state.get("mime_type") or "application/octet-stream")
        stored = self._store.put(data=data, name=filename, mime_type=mime_type)
        # ADR-0102: snake_case python keys matching the ``exportFile``
        # RenderContract (filename / path / mime_type / size / download_url).
        state = {
            "success": True,
            "path": normalized,
            "filename": stored.name,
            "download_url": stored.url,
            "mime_type": mime_type,
            "size": stored.size_bytes,
        }
        sandbox_file = SandboxFile(name=filename, mime_type=mime_type, data=data)
        return ComputerOpResult(
            success=True,
            content=f"Exported {filename} ({stored.size_bytes} bytes)",
            state=state,
            generated_files=(sandbox_file,),
        )


def _re_get(kind: str) -> Any:
    """Lazy import to break circular import (computer ↔ tools)."""
    if kind == "attachment_ids":
        from lca.layer0_infra.tools.run_attachment_scope import get_current_run_attachment_ids
        return get_current_run_attachment_ids()
    if kind == "inv":
        from lca.layer0_infra.tools.tool_invocation_scope import get_current_tool_invocation_id
        return get_current_tool_invocation_id()
    raise ValueError(kind)
