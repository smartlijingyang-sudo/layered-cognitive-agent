"""Host-backed local Sandbox — SANDBOX plane without Onlyboxes.

Implements the ``Sandbox`` protocol against a real workspace directory that
presents the guest contract root ``/mnt/data`` (or ``LCA_LOCAL_SANDBOX_ROOT``).
This is the production fallback when Onlyboxes credentials are unset: Host
sidecar stays MACHINE transport; Solo materializes ``runCommand`` /
``executeCode`` via BindingsView.sandbox rather than leaking Creator ``bash``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any

import structlog

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_MOUNT_ROOT,
    SANDBOX_OUTPUT_SUBDIR,
    SandboxFile,
    SandboxResult,
    SessionConfig,
    SessionInfo,
)
from lca.contracts.models.core.state.guest_layout import GuestLayout
from lca.infrastructure.sandbox.onlyboxes.bootstrap import safe_rel_name
from lca.infrastructure.sandbox.streaming.streaming import SandboxStreamEmitter

_log = structlog.get_logger(__name__)

_ENV_ROOT = "LCA_LOCAL_SANDBOX_ROOT"

_LANG_EXTENSION: dict[str, str] = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
}
_LANG_RUNNER: dict[str, str] = {
    "python": "python3",
    "javascript": "node",
    "typescript": "npx --yes tsx",
}


def default_local_root() -> str:
    """Resolve the host directory that backs the guest mount."""
    configured = os.getenv(_ENV_ROOT, "").strip()
    if configured:
        return configured
    # Prefer the canonical guest path when the process can write it
    # (ops may have prepared /mnt/data). Otherwise fall back to cache.
    try:
        path = Path(SANDBOX_MOUNT_ROOT)
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".lca-write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return str(path)
    except OSError:
        cache = Path.home() / ".cache" / "lca" / "local-sandbox" / "mnt" / "data"
        cache.mkdir(parents=True, exist_ok=True)
        return str(cache)


class LocalSandboxAdapter:
    """Host-backed Sandbox: real filesystem + subprocess shell/code exec."""

    name = "local-sandbox"

    def __init__(self, *, root: str | None = None, layout: GuestLayout | None = None) -> None:
        host_root = (root or default_local_root()).rstrip("/")
        self._host_root = host_root
        # Guest paths stay on SANDBOX_MOUNT_ROOT so prompts/tools agree with
        # Onlyboxes. When host_root differs, shell commands are rewritten.
        self._layout = layout if layout is not None else GuestLayout.from_root(SANDBOX_MOUNT_ROOT)
        self._sessions: dict[str, Path] = {}
        self._ensure_tree(Path(host_root))

    @property
    def host_root(self) -> str:
        return self._host_root

    def _ensure_tree(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        (root / SANDBOX_OUTPUT_SUBDIR).mkdir(parents=True, exist_ok=True)
        (root / ".lca" / "background").mkdir(parents=True, exist_ok=True)

    def _session_root(self, session_id: str = "") -> Path:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return Path(self._host_root)

    def _guest_to_host(self, guest_path: str, *, session_id: str = "") -> str:
        root = self._session_root(session_id)
        guest = guest_path.replace("\\", "/")
        mount = self._layout.root.rstrip("/")
        if guest == mount or guest.startswith(mount + "/"):
            rel = guest[len(mount) :].lstrip("/")
            return str(root / rel) if rel else str(root)
        if guest.startswith("/tmp/"):
            return guest
        return str(root / guest.lstrip("/"))

    def _rewrite_command(self, command: str) -> str:
        """Map guest ``/mnt/data`` references onto the host directory backing the mount.

        Absolute guest paths resolve against the mount root — that is where
        ``SandboxRuntime._stage_files`` writes run attachments, and what the
        tool surface advertises to the model. Mapping them onto the per-session
        cwd instead left ``runCommand`` unable to open an attachment that
        ``executeCode`` (whose paths live in the code body, never rewritten)
        could read fine. The session root stays the cwd, so relative writes
        such as ``outputs/report.pdf`` remain per-session.
        """
        mount = self._layout.root.rstrip("/")
        if self._host_root == mount:
            return command
        return command.replace(mount, self._host_root)

    async def _exec_shell(
        self,
        command: str,
        *,
        session_id: str = "",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        invocation_id: str = "",
        cwd: str | None = None,
    ) -> SandboxResult:
        emitter = SandboxStreamEmitter(invocation_id)
        work = cwd or str(self._session_root(session_id))
        Path(work).mkdir(parents=True, exist_ok=True)
        rewritten = self._rewrite_command(command)
        wrapped = f"cd {shlex.quote(work)} && {rewritten}"
        try:
            proc = await asyncio.create_subprocess_shell(
                wrapped,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            except TimeoutError:
                proc.kill()
                await proc.communicate()
                err = f"local sandbox timeout after {timeout_s}s"
                emitter.emit_stderr(err + "\n")
                return SandboxResult(success=False, exit_code=124, error=err, stderr=err + "\n")
        except OSError as exc:
            err = f"local sandbox spawn error: {type(exc).__name__}: {exc}"
            emitter.emit_stderr(err + "\n")
            return SandboxResult(success=False, exit_code=1, error=err, stderr=err + "\n")

        stdout = (stdout_b or b"").decode("utf-8", errors="replace")
        stderr = (stderr_b or b"").decode("utf-8", errors="replace")
        code = int(proc.returncode or 0)
        if stdout:
            emitter.emit_stdout(stdout)
        if stderr:
            emitter.emit_stderr(stderr)
        generated = self._collect_outputs(session_id=session_id)
        return SandboxResult(
            stdout=stdout,
            stderr=stderr,
            success=code == 0,
            exit_code=code,
            error="" if code == 0 else (stderr.strip() or f"exit code {code}"),
            generated_files=generated,
        )

    def _collect_outputs(self, *, session_id: str = "") -> tuple[SandboxFile, ...]:
        out_dir = self._session_root(session_id) / SANDBOX_OUTPUT_SUBDIR
        if not out_dir.is_dir():
            return ()
        files: list[SandboxFile] = []
        for path in sorted(out_dir.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            files.append(
                SandboxFile(name=path.name, mime_type="application/octet-stream", data=data)
            )
        return tuple(files)

    async def write_files(
        self,
        files: dict[str, bytes | str],
        *,
        base_dir: str = "",
        session_id: str = "",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
    ) -> SandboxResult:
        del timeout_s
        root_guest = base_dir or self._layout.root
        host_base = Path(self._guest_to_host(root_guest, session_id=session_id))
        host_base.mkdir(parents=True, exist_ok=True)
        (host_base / SANDBOX_OUTPUT_SUBDIR).mkdir(parents=True, exist_ok=True)
        for name, source in files.items():
            target = host_base / safe_rel_name(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(source, str) and source.startswith(("http://", "https://")):
                # Download via curl in the sandbox shell for parity with Onlyboxes.
                result = await self._exec_shell(
                    f"curl -fsSL {shlex.quote(source)} -o {shlex.quote(str(target))}",
                    session_id=session_id,
                )
                if not result.success:
                    return result
            else:
                raw = source if isinstance(source, bytes) else source.encode("utf-8")
                target.write_bytes(raw)
        return SandboxResult(success=True, exit_code=0)

    async def run(
        self,
        code: str,
        language: str = "python",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        return await self._run_code(
            code, language=language, timeout_s=timeout_s, session_id="", **kwargs
        )

    async def create_session(self, config: SessionConfig | None = None) -> SessionInfo | None:
        del config
        sid = new_id("lsess")
        path = Path(self._host_root) / ".sessions" / sid
        self._ensure_tree(path)
        # Also ensure canonical guest mount exists when host_root IS /mnt/data.
        self._ensure_tree(Path(self._host_root))
        self._sessions[sid] = path
        _log.info("local_sandbox_session_created", session_id=sid, root=str(path))
        return SessionInfo(session_id=sid, container_id=f"local:{sid}")

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        if session_id and session_id not in self._sessions:
            path = Path(self._host_root) / ".sessions" / session_id
            self._ensure_tree(path)
            self._sessions[session_id] = path
        return await self._run_code(
            code, language=language, timeout_s=timeout_s, session_id=session_id, **kwargs
        )

    async def destroy_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def run_terminal(
        self,
        command: str,
        *,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        invocation_id = str(kwargs.get("invocation_id", "") or "")
        session_id = str(kwargs.get("session_id", "") or "")
        return await self._exec_shell(
            command,
            session_id=session_id,
            timeout_s=timeout_s,
            invocation_id=invocation_id,
        )

    async def _run_code(
        self,
        code: str,
        *,
        language: str,
        timeout_s: int,
        session_id: str,
        **kwargs: Any,
    ) -> SandboxResult:
        lang_key = language.lower() if language else "python"
        ext = _LANG_EXTENSION.get(lang_key, "py")
        runner = _LANG_RUNNER.get(lang_key, "python3")
        work = self._session_root(session_id)
        fd, code_path = tempfile.mkstemp(prefix="lca-code-", suffix=f".{ext}", dir="/tmp")
        os.close(fd)
        try:
            Path(code_path).write_text(code, encoding="utf-8")
            return await self._exec_shell(
                f"{runner} {shlex.quote(code_path)}",
                session_id=session_id,
                timeout_s=timeout_s,
                invocation_id=str(kwargs.get("invocation_id", "") or ""),
                cwd=str(work),
            )
        finally:
            with contextlib.suppress(OSError):
                Path(code_path).unlink(missing_ok=True)


__all__ = ["LocalSandboxAdapter", "default_local_root"]
