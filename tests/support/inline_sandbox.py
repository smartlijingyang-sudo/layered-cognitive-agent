"""Test-only inline sandbox with /mnt/data VFS + session support."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import types
from typing import Any

from lca.contracts.models.core.sandbox import (
    SANDBOX_MOUNT_ROOT,
    SANDBOX_OUTPUT_SUBDIR,
    SandboxFile,
    SandboxResult,
    SessionConfig,
    SessionInfo,
)
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter


class InlineSandbox:
    """Virtual /mnt/data filesystem for unit tests (no Onlyboxes/Docker)."""

    def __init__(self, *, session_ok: bool = True) -> None:
        self.session_ok = session_ok
        self.run_calls: list[str] = []
        self.session_run_calls: list[tuple[str, str]] = []
        self.created_sessions: list[str] = []
        self.destroyed_sessions: list[str] = []
        self._counter = 0
        self._sessions: dict[str, dict[str, bytes]] = {}

    async def run(
        self,
        code: str,
        language: str = "python",
        files: dict[str, bytes] | None = None,
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        del language, timeout_s
        self.run_calls.append(code)
        vfs = self._seed_vfs(files)
        return self._exec(code, vfs, str(kwargs.get("invocation_id", "") or ""))

    async def create_session(self, config: SessionConfig | None = None) -> SessionInfo | None:
        if not self.session_ok:
            return None
        self._counter += 1
        sid = f"sess_{self._counter}"
        self.created_sessions.append(sid)
        self._sessions[sid] = self._seed_vfs(config.files if config else None)
        return SessionInfo(session_id=sid, container_id=f"ctr_{sid}")

    async def run_in_session(
        self,
        session_id: str,
        code: str,
        language: str = "python",
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        del language, timeout_s
        self.session_run_calls.append((session_id, code))
        vfs = self._sessions.setdefault(session_id, {})
        extra = kwargs.get("files")
        if isinstance(extra, dict):
            for name, data in extra.items():
                vfs[f"{SANDBOX_MOUNT_ROOT}/{name}"] = data
        return self._exec(code, vfs, str(kwargs.get("invocation_id", "") or ""))

    async def destroy_session(self, session_id: str) -> None:
        self.destroyed_sessions.append(session_id)
        self._sessions.pop(session_id, None)

    @staticmethod
    def _seed_vfs(files: dict[str, bytes] | None) -> dict[str, bytes]:
        vfs: dict[str, bytes] = {}
        for name, data in (files or {}).items():
            vfs[f"{SANDBOX_MOUNT_ROOT}/{name}"] = data
        return vfs

    def _exec(self, code: str, vfs: dict[str, bytes], invocation_id: str) -> SandboxResult:
        emitter = SandboxStreamEmitter(invocation_id)
        out_prefix = f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}/"

        def _open(path: str, mode: str = "r", *args: Any, **kw: Any):  # type: ignore[no-untyped-def]
            del args, kw
            path_s = str(path)
            if "b" in mode and "r" in mode:
                data = vfs.get(path_s, b"")
                return io.BytesIO(data)
            if "w" in mode or "a" in mode:
                buf = io.BytesIO()

                class _Writer:
                    def write(self, chunk: bytes | str) -> int:
                        if isinstance(chunk, str):
                            chunk = chunk.encode()
                        buf.write(chunk)
                        vfs[path_s] = buf.getvalue()
                        return len(chunk)

                    def __enter__(self) -> _Writer:
                        return self

                    def __exit__(self, *a: object) -> None:
                        vfs[path_s] = buf.getvalue()

                return _Writer()
            if "r" in mode:
                return io.StringIO(vfs.get(path_s, b"").decode(errors="replace"))
            raise FileNotFoundError(path_s)

        def _walk(top: str, *args: Any, **kw: Any):  # type: ignore[no-untyped-def]
            del args, kw
            base = top.rstrip("/")
            direct_files: list[str] = []
            subdirs: set[str] = set()
            for path in vfs:
                if not path.startswith(base + "/"):
                    continue
                rel = path[len(base) + 1 :]
                if not rel or rel.startswith("outputs/"):
                    continue
                parts = rel.split("/")
                if len(parts) == 1:
                    direct_files.append(parts[0])
                else:
                    subdirs.add(parts[0])
            for sub in sorted(subdirs):
                yield f"{base}/{sub}", [], []
            yield top, [], sorted(direct_files)

        def _getsize(path: str) -> int:
            return len(vfs.get(path, b""))

        def _makedirs(path: str, exist_ok: bool = False) -> None:
            return

        # Match real stdlib: getsize lives on os.path, not os.
        fake_path = type(
            "P",
            (),
            {
                "join": staticmethod(os.path.join),
                "relpath": staticmethod(os.path.relpath),
                "getsize": staticmethod(_getsize),
            },
        )()

        os_mod = types.ModuleType("os")
        os_mod.walk = _walk
        os_mod.path = fake_path
        os_mod.makedirs = _makedirs
        prev_os = sys.modules.get("os")
        sys.modules["os"] = os_mod

        g: dict[str, Any] = {
            "open": _open,
            "print": print,
            "__builtins__": __builtins__,
            "os": os_mod,
        }

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(code, "<inline>", "exec"), g, g)  # noqa: S102
            stdout = buf.getvalue()
            if stdout:
                emitter.emit_stdout(stdout)
            generated = [
                SandboxFile(
                    name=path.rsplit("/", 1)[-1],
                    mime_type="application/octet-stream",
                    data=data,
                )
                for path, data in vfs.items()
                if path.startswith(out_prefix)
            ]
            return SandboxResult(
                stdout=stdout,
                success=True,
                exit_code=0,
                generated_files=tuple(generated),
            )
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            emitter.emit_stderr(err + "\n")
            return SandboxResult(success=False, exit_code=1, error=err, stderr=err + "\n")
        finally:
            if prev_os is not None:
                sys.modules["os"] = prev_os
            else:
                sys.modules.pop("os", None)
