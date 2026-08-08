"""Deterministic in-process test double — NOT a security boundary (ADR-0044).

Use for unit tests and explicit offline demos only. Real isolation requires
``E2BSandboxAdapter`` (cloud) or ``LocalSandboxAdapter`` (microsandbox microVM).
"""

from __future__ import annotations

import traceback
from typing import Any

from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SandboxFile,
    SandboxResult,
)
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter


class MockSandboxAdapter(Sandbox):
    """In-process Python ``exec`` with a restricted builtin set (test double).

    Emits ``SandboxOutputDelta`` lines when ``invocation_id`` is provided so
    the journal → SSE path can be exercised without real sandbox credentials.
    This is **not** process/VM isolation — never treat it as a sandbox fallback.
    """

    name = "mock-sandbox"

    async def run(
        self,
        code: str,
        language: str = "python",
        files: dict[str, bytes] | None = None,
        timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S,
        **kwargs: Any,
    ) -> SandboxResult:
        del timeout_s  # mock is instantaneous; timeout reserved for Protocol parity
        if language and language.lower() not in {"python", "py"}:
            return SandboxResult(
                success=False,
                exit_code=1,
                error=f"MockSandboxAdapter only supports python, got {language!r}",
            )

        invocation_id = str(kwargs.get("invocation_id", "") or "")
        emitter = SandboxStreamEmitter(invocation_id)
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        generated: list[SandboxFile] = []

        def _write_stdout(text: object) -> None:
            line = str(text)
            stdout_chunks.append(line)
            emitter.emit_stdout(line)

        def _write_stderr(text: object) -> None:
            line = str(text)
            stderr_chunks.append(line)
            emitter.emit_stderr(line)

        def _print(*args: object, **print_kwargs: Any) -> None:
            sep = str(print_kwargs.get("sep", " "))
            end = str(print_kwargs.get("end", "\n"))
            _write_stdout(sep.join(str(a) for a in args) + end)

        def _save(name: str, data: bytes, mime_type: str = "application/octet-stream") -> None:
            generated.append(SandboxFile(name=name, mime_type=mime_type, data=data))

        mounted = dict(files or {})
        safe_builtins: dict[str, Any] = {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "int": int,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "print": _print,
            "range": range,
            "repr": repr,
            "round": round,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        }
        # Single dict so user code can see mounted_files / save_file as globals.
        namespace: dict[str, Any] = {
            "__name__": "__sandbox__",
            "__builtins__": safe_builtins,
            "mounted_files": mounted,
            "save_file": _save,
            "print": _print,
        }

        try:
            exec(compile(code, "<sandbox>", "exec"), namespace, namespace)  # noqa: S102
        except Exception as exc:
            tb = traceback.format_exc()
            _write_stderr(tb)
            return SandboxResult(
                stdout="".join(stdout_chunks),
                stderr="".join(stderr_chunks),
                exit_code=1,
                success=False,
                generated_files=tuple(generated),
                error=f"{type(exc).__name__}: {exc}",
            )

        return SandboxResult(
            stdout="".join(stdout_chunks),
            stderr="".join(stderr_chunks),
            exit_code=0,
            success=True,
            generated_files=tuple(generated),
        )
