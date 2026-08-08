"""E2B Code Interpreter adapter — production sandbox with live stdout/stderr journal."""

from __future__ import annotations

import asyncio
import base64
import contextvars
import logging
from typing import Any

from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_MOUNT_ROOT,
    SandboxFile,
    SandboxResult,
)
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

_log = logging.getLogger(__name__)


def _message_line(data: Any) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data if data.endswith("\n") else f"{data}\n"
    line = getattr(data, "line", None)
    if line is not None:
        text = str(line)
        return text if text.endswith("\n") else f"{text}\n"
    return str(data)


def _collect_result_files(execution: Any) -> list[SandboxFile]:
    """Map E2B rich results (charts, text blobs) into SandboxFile rows when possible."""
    out: list[SandboxFile] = []
    results = getattr(execution, "results", None) or []
    for index, item in enumerate(results):
        png = getattr(item, "png", None)
        if png:
            try:
                raw = base64.b64decode(png)
            except (TypeError, ValueError):
                continue
            out.append(
                SandboxFile(
                    name=f"result_{index}.png",
                    mime_type="image/png",
                    data=raw,
                )
            )
            continue
        chart = getattr(item, "chart", None)
        if chart is not None and hasattr(chart, "png") and chart.png:
            try:
                raw = base64.b64decode(chart.png)
            except (TypeError, ValueError):
                continue
            out.append(
                SandboxFile(
                    name=f"chart_{index}.png",
                    mime_type="image/png",
                    data=raw,
                )
            )
            continue
        text = getattr(item, "text", None)
        if isinstance(text, str) and text.strip():
            out.append(
                SandboxFile(
                    name=f"result_{index}.txt",
                    mime_type="text/plain",
                    data=text.encode("utf-8"),
                )
            )
    return out


class E2BSandboxAdapter(Sandbox):
    """E2B-backed Sandbox; emits SandboxOutputDelta from on_stdout / on_stderr."""

    name = "e2b-sandbox"

    def __init__(self, *, api_key: str | None = None) -> None:
        self._api_key = api_key

    async def run(
        self,
        code: str,
        language: str = "python",
        files: dict[str, bytes] | None = None,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        if language and language.lower() not in {"python", "py"}:
            return SandboxResult(
                success=False,
                exit_code=1,
                error=f"E2BSandboxAdapter MVP supports python only, got {language!r}",
            )

        invocation_id = str(kwargs.get("invocation_id", "") or "")
        # Capture ambient RunScope / hub so worker-thread callbacks still stamp correctly.
        ctx = contextvars.copy_context()
        return await asyncio.to_thread(
            ctx.run,
            self._run_sync,
            code,
            files or {},
            int(timeout_s),
            invocation_id,
        )

    def _run_sync(
        self,
        code: str,
        files: dict[str, bytes],
        timeout_s: int,
        invocation_id: str,
    ) -> SandboxResult:
        try:
            # Optional dependency group ``sandbox-e2b``; importlib avoids hard mypy dep.
            import importlib

            sandbox_mod = importlib.import_module("e2b_code_interpreter")
            sandbox_cls = sandbox_mod.Sandbox
        except ImportError:  # pragma: no cover - optional dependency
            return SandboxResult(
                success=False,
                exit_code=1,
                error=(
                    "e2b-code-interpreter is not installed. "
                    "Install with: uv sync --group sandbox-e2b"
                ),
            )

        emitter = SandboxStreamEmitter(invocation_id)
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        def on_stdout(data: Any) -> None:
            line = _message_line(data)
            stdout_parts.append(line)
            emitter.emit_stdout(line)

        def on_stderr(data: Any) -> None:
            line = _message_line(data)
            stderr_parts.append(line)
            emitter.emit_stderr(line)

        sandbox = None
        try:
            create_kwargs: dict[str, Any] = {"timeout": timeout_s}
            if self._api_key:
                create_kwargs["api_key"] = self._api_key
            sandbox = sandbox_cls.create(**create_kwargs)

            for rel_path, content in files.items():
                remote = f"{SANDBOX_MOUNT_ROOT}/{rel_path.lstrip('/')}"
                # Ensure parent dirs exist when the SDK supports it; write is best-effort.
                try:
                    sandbox.files.write(remote, content)
                except Exception as write_exc:  # pragma: no cover - provider surface
                    _log.warning("e2b_file_mount_failed path=%s error=%s", remote, write_exc)
                    emitter.emit_stderr(f"[lca] failed to mount {rel_path}: {write_exc}\n")

            execution = sandbox.run_code(
                code,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
                timeout=timeout_s,
            )
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
                    sandbox.kill()
                except Exception:  # pragma: no cover
                    _log.debug("e2b_sandbox_kill_failed", exc_info=True)

        exec_error = getattr(execution, "error", None)
        error_text = ""
        if exec_error is not None:
            error_text = str(
                getattr(exec_error, "value", None)
                or getattr(exec_error, "name", None)
                or exec_error
            )
            if error_text and not stderr_parts:
                emitter.emit_stderr(error_text + "\n")
                stderr_parts.append(error_text + "\n")

        # Prefer live-captured streams; fall back to aggregated logs if callbacks were quiet.
        logs = getattr(execution, "logs", None)
        if logs is not None and not stdout_parts:
            for line in getattr(logs, "stdout", None) or []:
                text = line if isinstance(line, str) else str(line)
                if not text.endswith("\n"):
                    text += "\n"
                stdout_parts.append(text)
        if logs is not None and not stderr_parts:
            for line in getattr(logs, "stderr", None) or []:
                text = line if isinstance(line, str) else str(line)
                if not text.endswith("\n"):
                    text += "\n"
                stderr_parts.append(text)

        generated = _collect_result_files(execution)
        success = exec_error is None
        return SandboxResult(
            stdout="".join(stdout_parts),
            stderr="".join(stderr_parts),
            exit_code=0 if success else 1,
            success=success,
            generated_files=tuple(generated),
            error=error_text,
        )
