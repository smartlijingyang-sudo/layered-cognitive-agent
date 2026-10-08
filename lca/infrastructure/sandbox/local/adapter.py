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
from lca.contracts.protocols import Sandbox
from lca.infrastructure.sandbox.onlyboxes.bootstrap import safe_rel_name
from lca.infrastructure.sandbox.output.collect import try_append_generated_file
from lca.infrastructure.sandbox.paths.mount_namespace import (
    mount_namespace_enabled,
    wrap_in_mount_namespace,
)
from lca.infrastructure.sandbox.paths.sandbox_paths import SandboxPaths
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
    """Resolve the host directory that backs the guest mount.

    Delegates to the workspace SSOT
    (:func:`lca.infrastructure.path.locator.assistant_workspace_root`);
    kept as a thin wrapper for backward compatibility.
    """
    from lca.infrastructure.path.locator import assistant_workspace_root

    return str(assistant_workspace_root())


def _ensure_dir(path: Path) -> None:
    """阻塞式建目录；沙箱文件 I/O 本就是阻塞子进程路径，同步执行。"""
    path.mkdir(parents=True, exist_ok=True)


def _write_text_blocking(path: Path, text: str) -> None:
    """阻塞式写文本；配合子进程执行，避免 async pathlib 依赖。"""
    path.write_text(text, encoding="utf-8")


def _unlink_blocking(path: Path) -> None:
    """幂等删除临时文件（阻塞式）。"""
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


class UnknownSandboxSessionError(ValueError):
    """run_in_session got a session_id that create_session never issued (RA-037).

    Fail-loud instead of silently rebuilding a directory under the boot-time
    host root: an unknown id is always a caller bug (stale or destroyed
    session), and executing code under the wrong directory is the worst
    possible outcome. Callers must go through create_session() first.
    """


class LocalSandboxAdapter(Sandbox):
    """Host-backed Sandbox: real filesystem + subprocess shell/code exec."""

    name = "local-sandbox"

    def __init__(
        self,
        *,
        root: str | None = None,
        layout: GuestLayout | None = None,
        mount_namespace: bool | None = None,
    ) -> None:
        host_root = (root or default_local_root()).rstrip("/")
        self._host_root = host_root
        # Explicit per-exec mount-namespace mode override; None means
        # auto-detect (mount_namespace_enabled: env var, else probe).
        self._mount_namespace_override = mount_namespace
        # Guest paths stay on SANDBOX_MOUNT_ROOT so prompts/tools agree with
        # Onlyboxes. When host_root differs, shell commands are translated:
        # string rewriting in virtual mode, kernel bind mount in per-exec
        # mount-namespace mode (todo-81 (c)).
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

    def _mount_ns_mode(self) -> bool:
        """Per-exec mount-namespace mode for this adapter (todo-81 (c)).

        Explicit constructor arg wins, then ``LCA_SANDBOX_MOUNT_NS``, then
        auto-detect (unshare/userns probe). When False, exec falls back to
        the (b) virtual string-mapping path — the agent sees the same
        ``/mnt/data`` namespace either way.
        """
        if self._mount_namespace_override is not None:
            return self._mount_namespace_override
        return mount_namespace_enabled()

    def _paths_for(self, session_id: str = "") -> SandboxPaths:
        """Single-seam path mapping for one session (todo-81).

        The only place that knows how the agent-visible guest mount maps
        onto this machine; every boundary crossing below derives from it.
        """
        return SandboxPaths.for_local(
            self._session_root(session_id),
            guest_mount=self._layout.root.rstrip("/"),
            mounted=self._mount_ns_mode(),
        )

    def _wrap_command(self, command: str, paths: SandboxPaths, work: str) -> str:
        """Wrap the guest command for execution.

        Mounted mode (todo-81 (c)): per-exec ``unshare -Urm`` with the work
        dir bind-mounted at the guest mount (Pattern A — no holder). The
        kernel translates, so ``command`` is already guest-native
        (``rewrite_command`` is identity in this mode).
        Virtual mode: plain ``cd`` into the host work dir; translation is
        done by ``SandboxPaths.rewrite_command`` string rewriting.
        """
        if paths.mounted:
            return wrap_in_mount_namespace(
                command,
                session_dir=str(paths.host_root),
                guest_mount=paths.guest_mount,
            )
        return f"cd {shlex.quote(work)} && {command}"

    def _guest_to_host(self, guest_path: str, *, session_id: str = "") -> str:
        return str(self._paths_for(session_id).resolve(guest_path))

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
        _ensure_dir(Path(work))
        paths = SandboxPaths.for_local(
            work,
            guest_mount=self._layout.root.rstrip("/"),
            mounted=self._mount_ns_mode(),
        )
        rewritten = paths.rewrite_command(command)
        wrapped = self._wrap_command(rewritten, paths, work)
        # Guest scripts read ROOT from this var. Virtual mode: the host
        # session dir (guest code runs on the host, strings were rewritten).
        # Mounted mode: the guest mount itself — inside the namespace that
        # path really is the session dir, and host paths must stay invisible
        # to the guest (axiom 1).
        # Single source (todo-81): derived from the seam in both modes.
        env = {
            **os.environ,
            "LCA_GUEST_ROOT": paths.guest_mount if paths.mounted else str(paths.host_root),
        }
        try:
            proc = await asyncio.create_subprocess_shell(
                wrapped,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work,
                env=env,
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

        stdout = paths.present_text((stdout_b or b"").decode("utf-8", errors="replace"))
        stderr = paths.present_text((stderr_b or b"").decode("utf-8", errors="replace"))
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
        diagnostics: list[str] = []
        for path in sorted(out_dir.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if not try_append_generated_file(files, diagnostics, name=path.name, data=data):
                break
        if diagnostics:
            _log.warning("local_sandbox_output_capped", diagnostics="".join(diagnostics))
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
        _ensure_dir(host_base)
        _ensure_dir(host_base / SANDBOX_OUTPUT_SUBDIR)
        for name, source in files.items():
            target = host_base / safe_rel_name(name)
            _ensure_dir(target.parent)
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
        # Per-run workspace SSOT: the caller resolves the run assistant's
        # workspace inside the run scope; the boot-time default root only
        # backs sessions created without that binding.
        root = (
            config.workspace_root.rstrip("/")
            if config and config.workspace_root
            else self._host_root
        )
        sid = new_id("lsess")
        path = Path(root) / ".sessions" / sid
        self._ensure_tree(path)
        # Also ensure canonical guest mount exists when root IS /mnt/data.
        self._ensure_tree(Path(root))
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
        """Execute code inside a session created by create_session().

        RA-037: an unknown non-empty session_id raises
        UnknownSandboxSessionError instead of silently rebuilding a
        directory under the boot-time host root. The empty session_id ""
        is the explicit stateless fallback: code runs under the boot-time
        host root with no per-session isolation (degraded — callers that
        need isolation must create_session() first).
        """
        if session_id and session_id not in self._sessions:
            raise UnknownSandboxSessionError(
                f"local sandbox: unknown session_id {session_id!r} — "
                "call create_session() first; refusing to rebuild under the boot root"
            )
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
            _write_text_blocking(Path(code_path), code)
            return await self._exec_shell(
                f"{runner} {shlex.quote(code_path)}",
                session_id=session_id,
                timeout_s=timeout_s,
                invocation_id=str(kwargs.get("invocation_id", "") or ""),
                cwd=str(work),
            )
        finally:
            _unlink_blocking(Path(code_path))


__all__ = ["LocalSandboxAdapter", "UnknownSandboxSessionError", "default_local_root"]
