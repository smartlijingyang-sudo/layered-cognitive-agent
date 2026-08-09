"""Onlyboxes-backed sandbox — console REST + pythonExec.

Auth: ``Authorization: Bearer <access token>`` against console HTTP.
Execution: ``POST /api/v1/tasks`` capability ``pythonExec``.

Input files are staged under ``/mnt/data/<name>`` by a bootstrap preamble
embedded in the submitted code; products under ``/mnt/data/outputs/`` are
harvested via a trailing base64 artifact block (ADR-0046 path contract).
"""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from lca.contracts.models.core.sandbox import (
    DEFAULT_SANDBOX_TIMEOUT_S,
    SANDBOX_MOUNT_ROOT,
    SandboxResult,
)
from lca.contracts.protocols import Sandbox
from lca.layer0_infra.sandbox.onlyboxes_artifacts import (
    ARTIFACT_BEGIN,
    ARTIFACT_END,
    strip_artifacts,
)
from lca.layer0_infra.sandbox.output_collect import sandbox_output_dir
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

_PYTHON_LANGUAGES = frozenset({"python", "py"})
_CAPABILITY_PYTHON = "pythonExec"
_TASK_MODE_SYNC = "sync"
_MAX_WAIT_MS = 60_000
_MAX_TIMEOUT_MS = 600_000
_STATUS_SUCCEEDED = "succeeded"


def _timeout_ms(timeout_s: int) -> int:
    ms = max(1, int(timeout_s) * 1000)
    return min(ms, _MAX_TIMEOUT_MS)


def _wait_ms(timeout_s: int) -> int:
    return min(_timeout_ms(timeout_s), _MAX_WAIT_MS)


def _safe_rel_name(name: str) -> str:
    """Strip path traversal; keep basename for guest mount."""
    cleaned = name.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return parts[-1] if parts else "file.bin"


def _strip_surrogates(text: str) -> str:
    """Replace lone surrogate code points (U+D800–U+DFFF) with U+FFFD."""
    return "".join("\ufffd" if "\ud800" <= ch <= "\udfff" else ch for ch in text)


def _build_wrapped_code(code: str, files: dict[str, bytes] | None) -> str:
    """Bootstrap mounts + harvest outputs around user code."""
    mount_items: list[tuple[str, str]] = []
    for raw_name, data in (files or {}).items():
        name = _safe_rel_name(raw_name)
        mount_items.append((name, base64.b64encode(data).decode("ascii")))

    mounts_literal = json.dumps(mount_items, ensure_ascii=False)
    out_dir = sandbox_output_dir()
    # Keep user source as a triple-quoted string + exec so indentation is free.
    # Strip surrogate code points first — compile() requires valid UTF-8.
    user_literal = json.dumps(_strip_surrogates(code))

    return f"""# --- LCA Onlyboxes bootstrap (do not edit) ---
import base64 as _lca_b64
import json as _lca_json
import os as _lca_os
import traceback as _lca_tb
from pathlib import Path as _lca_Path

_LCA_MOUNT = {SANDBOX_MOUNT_ROOT!r}
_LCA_OUT = {out_dir!r}
_LCA_MOUNTS = {mounts_literal}
_LCA_USER_CODE = {user_literal}
_lca_os.makedirs(_LCA_MOUNT, exist_ok=True)
_lca_os.makedirs(_LCA_OUT, exist_ok=True)
for _lca_name, _lca_b64s in _LCA_MOUNTS:
    _lca_path = _lca_Path(_LCA_MOUNT) / _lca_name
    _lca_path.write_bytes(_lca_b64.b64decode(_lca_b64s))

_lca_user_failed = False
try:
    exec(compile(_LCA_USER_CODE, "<lca-user>", "exec"), {{"__name__": "__main__"}})
except SystemExit as _lca_se:
    if _lca_se.code not in (0, None):
        _lca_user_failed = True
except Exception:
    _lca_user_failed = True
    _lca_tb.print_exc()

_lca_arts = []
try:
    for _lca_root, _lca_dirs, _lca_files in _lca_os.walk(_LCA_OUT):
        for _lca_fn in _lca_files:
            _lca_fp = _lca_os.path.join(_lca_root, _lca_fn)
            try:
                with open(_lca_fp, "rb") as _lca_fh:
                    _lca_raw = _lca_fh.read()
            except OSError:
                continue
            _lca_arts.append({{
                "name": _lca_fn,
                "b64": _lca_b64.b64encode(_lca_raw).decode("ascii"),
            }})
except Exception as _lca_harv_exc:
    print(f"[lca] harvest failed: {{_lca_harv_exc}}", flush=True)
print({ARTIFACT_BEGIN!r} + _lca_json.dumps(_lca_arts, ensure_ascii=False) + {ARTIFACT_END!r}, flush=True)
if _lca_user_failed:
    raise SystemExit(1)
"""


class OnlyboxesSandboxAdapter(Sandbox):
    """HTTP client for Onlyboxes console pythonExec."""

    name = "onlyboxes-sandbox"

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._access_token = access_token
        self._client = client

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
                error=f"OnlyboxesSandboxAdapter supports python only, got {language!r}",
            )

        invocation_id = str(kwargs.get("invocation_id", "") or "")
        emitter = SandboxStreamEmitter(invocation_id)
        wrapped = _build_wrapped_code(code, files)
        timeout_ms = _timeout_ms(timeout_s)
        wait_ms = _wait_ms(timeout_s)
        body = {
            "capability": _CAPABILITY_PYTHON,
            "input": {"code": wrapped, "timeout_ms": timeout_ms},
            "mode": _TASK_MODE_SYNC,
            "wait_ms": wait_ms,
            "timeout_ms": timeout_ms,
        }

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=httpx.Timeout((timeout_ms / 1000.0) + 15.0)
        )
        try:
            try:
                response = await client.post(
                    f"{self._base_url}/api/v1/tasks",
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            except httpx.HTTPError as exc:
                err = f"Onlyboxes transport error: {type(exc).__name__}: {exc}"
                emitter.emit_stderr(err + "\n")
                return SandboxResult(success=False, exit_code=1, error=err, stderr=err + "\n")

            text = response.text
            try:
                payload: Any = json.loads(text) if text else {}
            except json.JSONDecodeError:
                err = f"Onlyboxes non-JSON response HTTP {response.status_code}: {text[:300]}"
                emitter.emit_stderr(err + "\n")
                return SandboxResult(success=False, exit_code=1, error=err, stderr=err + "\n")

            if not isinstance(payload, dict):
                err = f"Onlyboxes unexpected payload type: {type(payload).__name__}"
                return SandboxResult(success=False, exit_code=1, error=err)

            if response.status_code >= 400 and "result" not in payload:
                err_msg = payload.get("error")
                if isinstance(err_msg, dict):
                    message = str(err_msg.get("message") or err_msg.get("code") or err_msg)
                else:
                    message = str(err_msg or f"HTTP {response.status_code}")
                emitter.emit_stderr(message + "\n")
                return SandboxResult(
                    success=False,
                    exit_code=1,
                    error=message,
                    stderr=message + "\n",
                )

            status = str(payload.get("status") or "")
            raw_result = payload.get("result")
            result_obj: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
            raw_error = payload.get("error")
            task_error: dict[str, Any] | None = raw_error if isinstance(raw_error, dict) else None

            stdout_raw = str(result_obj.get("output") or result_obj.get("stdout") or "")
            stderr_raw = str(result_obj.get("stderr") or "")
            exit_code_raw = result_obj.get("exit_code")
            try:
                exit_code = (
                    int(exit_code_raw)
                    if exit_code_raw is not None
                    else (0 if status == _STATUS_SUCCEEDED else 1)
                )
            except (TypeError, ValueError):
                exit_code = 1

            cleaned_stdout, generated, diags = strip_artifacts(stdout_raw)
            if diags:
                stderr_raw = stderr_raw + "".join(diags)
            if cleaned_stdout:
                emitter.emit_stdout(cleaned_stdout)
            if stderr_raw:
                emitter.emit_stderr(stderr_raw)

            if task_error:
                error_text = str(task_error.get("message") or task_error.get("code") or task_error)
            elif exit_code != 0:
                error_text = stderr_raw.strip() or f"exit_code={exit_code}"
            elif status and status != _STATUS_SUCCEEDED:
                error_text = f"Onlyboxes task status={status!r}"
            else:
                error_text = ""

            success = exit_code == 0 and status in {_STATUS_SUCCEEDED, ""} and task_error is None
            return SandboxResult(
                stdout=cleaned_stdout,
                stderr=stderr_raw,
                exit_code=exit_code,
                success=success,
                generated_files=tuple(generated),
                error=error_text if not success else "",
            )
        finally:
            if owns_client:
                await client.aclose()
