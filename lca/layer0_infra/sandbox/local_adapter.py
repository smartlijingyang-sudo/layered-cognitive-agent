"""microsandbox-backed local sandbox — microVM isolation, no daemon required.

Optional dependency group ``sandbox-local``. Hardware-level isolation via
libkrun (Linux KVM / macOS Apple Silicon). Not a silent fallback for E2B —
selected only via ``LCA_SANDBOX_BACKEND=local`` (ADR-0044).
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_MOUNT_ROOT,
    SandboxResult,
)
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

_log = logging.getLogger(__name__)

_DEFAULT_IMAGE = "python"
_DEFAULT_CPUS = 1
_DEFAULT_MEMORY_MIB = 512

_SANDBOX_NAME_MAX = 128
_NAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9_-]+")

_EVENT_STDOUT = "stdout"
_EVENT_STDERR = "stderr"
_EVENT_EXITED = "exited"
_EVENT_FAILED = "failed"

_PYTHON_LANGUAGES = frozenset({"python", "py"})


def _decode_stream_bytes(data: bytes | None) -> str:
    if not data:
        return ""
    return data.decode("utf-8", errors="replace")


def _sandbox_name(invocation_id: str) -> str:
    """Build a unique microsandbox name (≤128 UTF-8 bytes, name-safe)."""
    token = _NAME_SAFE_RE.sub("-", invocation_id).strip("-") if invocation_id else ""
    if not token:
        token = uuid.uuid4().hex[:12]
    # Keep room for "lca-" prefix.
    prefix = "lca-"
    budget = _SANDBOX_NAME_MAX - len(prefix)
    return f"{prefix}{token[:budget]}"


class LocalSandboxAdapter(Sandbox):
    """microsandbox-backed Sandbox — same Protocol as E2B, runs as a local microVM."""

    name = "local-sandbox"

    def __init__(
        self,
        *,
        image: str = _DEFAULT_IMAGE,
        cpus: int = _DEFAULT_CPUS,
        memory_mib: int = _DEFAULT_MEMORY_MIB,
    ) -> None:
        self._image = image
        self._cpus = cpus
        self._memory_mib = memory_mib

    async def run(
        self,
        code: str,
        language: str = "python",
        files: dict[str, bytes] | None = None,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        if language and language.lower() not in _PYTHON_LANGUAGES:
            return SandboxResult(
                success=False,
                exit_code=1,
                error=f"LocalSandboxAdapter MVP supports python only, got {language!r}",
            )

        try:
            import importlib

            msb = importlib.import_module("microsandbox")
        except ImportError:  # pragma: no cover - optional dependency
            return SandboxResult(
                success=False,
                exit_code=1,
                error=(
                    "microsandbox is not installed. Install with: uv sync --group sandbox-local"
                ),
            )

        invocation_id = str(kwargs.get("invocation_id", "") or "")
        emitter = SandboxStreamEmitter(invocation_id)
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        exit_code = 1
        error_text = ""

        create_kwargs: dict[str, Any] = {
            "image": self._image,
            "cpus": self._cpus,
            "memory": self._memory_mib,
            "replace": True,
        }
        # Optional Network.none() when present — isolate untrusted agent code.
        network_cls = getattr(msb, "Network", None)
        if network_cls is not None and hasattr(network_cls, "none"):
            create_kwargs["network"] = network_cls.none()

        # Ensure mount root exists before guest fs writes.
        patch_cls = getattr(msb, "Patch", None)
        if files and patch_cls is not None and hasattr(patch_cls, "mkdir"):
            create_kwargs["patches"] = [patch_cls.mkdir(SANDBOX_MOUNT_ROOT, mode=0o755)]

        sandbox = None
        try:
            sandbox = await msb.Sandbox.create(
                _sandbox_name(invocation_id),
                **create_kwargs,
            )
            fs = sandbox.fs
            for rel_path, content in (files or {}).items():
                remote = f"{SANDBOX_MOUNT_ROOT}/{rel_path.lstrip('/')}"
                try:
                    await fs.write(remote, content)
                except Exception as write_exc:  # pragma: no cover - provider surface
                    _log.warning(
                        "local_sandbox_file_mount_failed path=%s error=%s",
                        remote,
                        write_exc,
                    )
                    emitter.emit_stderr(f"[lca] failed to mount {rel_path}: {write_exc}\n")

            handle = await sandbox.exec_stream(
                "python3",
                ["-c", code],
                timeout=float(timeout_s),
            )
            async for event in handle:
                event_type = getattr(event, "event_type", None)
                if event_type == _EVENT_STDOUT:
                    text = _decode_stream_bytes(getattr(event, "data", None))
                    if text:
                        stdout_parts.append(text)
                        emitter.emit_stdout(text)
                elif event_type == _EVENT_STDERR:
                    text = _decode_stream_bytes(getattr(event, "data", None))
                    if text:
                        stderr_parts.append(text)
                        emitter.emit_stderr(text)
                elif event_type == _EVENT_EXITED:
                    code_val = getattr(event, "code", None)
                    exit_code = int(code_val) if code_val is not None else 0
                    break
                elif event_type == _EVENT_FAILED:
                    fail_msg = _decode_stream_bytes(getattr(event, "data", None))
                    code_val = getattr(event, "code", None)
                    exit_code = int(code_val) if code_val is not None else 1
                    if fail_msg:
                        error_text = fail_msg
                        stderr_parts.append(
                            fail_msg if fail_msg.endswith("\n") else fail_msg + "\n"
                        )
                        emitter.emit_stderr(stderr_parts[-1])
                    break
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            emitter.emit_stderr(err + "\n")
            return SandboxResult(
                stdout="".join(stdout_parts),
                stderr="".join(stderr_parts) + err + "\n",
                exit_code=1,
                success=False,
                error=err,
            )
        finally:
            if sandbox is not None:
                try:
                    await sandbox.stop()
                except Exception:  # pragma: no cover
                    _log.debug("local_sandbox_cleanup_failed", exc_info=True)

        return SandboxResult(
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            exit_code=exit_code,
            success=exit_code == 0,
            error=error_text,
        )
