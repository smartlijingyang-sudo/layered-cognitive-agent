"""Onlyboxes shared constants, code bootstrap, and response parsing.

Extracted from ``onlyboxes_adapter`` so that both the stateless adapter and
the session module can share these without circular imports.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from lca.contracts.models.core.sandbox import (
    SANDBOX_MOUNT_ROOT,
    SandboxResult,
)
from lca.layer0_infra.sandbox.onlyboxes_artifacts import (
    ARTIFACT_BEGIN,
    ARTIFACT_END,
    strip_artifacts,
)
from lca.layer0_infra.sandbox.output_collect import sandbox_output_dir
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter
from lca.layer0_infra.text.safe_boundary import sanitize_stream_text

# ── constants ───────────────────────────────────────────────────────

PYTHON_LANGUAGES: frozenset[str] = frozenset({"python", "py"})
CAPABILITY_PYTHON = "pythonExec"
TASK_MODE_SYNC = "sync"
MAX_WAIT_MS = 60_000
MAX_TIMEOUT_MS = 600_000
STATUS_SUCCEEDED = "succeeded"

# ── helpers ─────────────────────────────────────────────────────────


def timeout_ms(timeout_s: int) -> int:
    ms = max(1, int(timeout_s) * 1000)
    return min(ms, MAX_TIMEOUT_MS)


def wait_ms(timeout_s: int) -> int:
    return min(timeout_ms(timeout_s), MAX_WAIT_MS)


def safe_rel_name(name: str) -> str:
    """Strip path traversal; keep basename for guest mount."""
    cleaned = name.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return parts[-1] if parts else "file.bin"


def auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }


def _strip_surrogates(text: str) -> str:
    """Replace lone surrogate code points (U+D800–U+DFFF) with U+FFFD."""
    return "".join("\ufffd" if "\ud800" <= ch <= "\udfff" else ch for ch in text)


def build_wrapped_code(code: str, files: dict[str, bytes] | None) -> str:
    """Bootstrap mounts + harvest outputs around user code."""
    mount_items: list[tuple[str, str]] = []
    for raw_name, data in (files or {}).items():
        name = safe_rel_name(raw_name)
        mount_items.append((name, base64.b64encode(data).decode("ascii")))

    mounts_literal = json.dumps(mount_items, ensure_ascii=False)
    out_dir = sandbox_output_dir()
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

# Patch json.dumps to handle numpy/pandas types (int64, float64, etc.)
_lca_original_dumps = _lca_json.dumps
def _lca_numpy_dumps(obj, *args, **kwargs):
    def _numpy_default(o):
        if hasattr(o, "item"):
            return o.item()
        raise TypeError(f"Object of type {{type(o).__name__}} is not JSON serializable")
    kwargs.setdefault("default", _numpy_default)
    return _lca_original_dumps(obj, *args, **kwargs)
_lca_json.dumps = _lca_numpy_dumps

# Suppress matplotlib font warnings (sandbox lacks full font weights)
import warnings as _lca_warnings
_lca_warnings.filterwarnings("ignore", module="matplotlib.font_manager")

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


# ── response parser ─────────────────────────────────────────────────


def parse_exec_response(response: httpx.Response, emitter: SandboxStreamEmitter) -> SandboxResult:
    """Parse an Onlyboxes exec/session response into a SandboxResult."""
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
        return SandboxResult(success=False, exit_code=1, error=message, stderr=message + "\n")

    status = str(payload.get("status") or "")
    raw_result = payload.get("result")
    result_obj: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
    raw_error = payload.get("error")
    task_error: dict[str, Any] | None = raw_error if isinstance(raw_error, dict) else None

    stdout_raw = sanitize_stream_text(
        str(result_obj.get("output") or result_obj.get("stdout") or "")
    )
    stderr_raw = sanitize_stream_text(str(result_obj.get("stderr") or ""))
    exit_code_raw = result_obj.get("exit_code")
    try:
        exit_code = (
            int(exit_code_raw)
            if exit_code_raw is not None
            else (0 if status == STATUS_SUCCEEDED else 1)
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
    elif status and status != STATUS_SUCCEEDED:
        error_text = f"Onlyboxes task status={status!r}"
    else:
        error_text = ""

    success = exit_code == 0 and status in {STATUS_SUCCEEDED, ""} and task_error is None
    return SandboxResult(
        stdout=cleaned_stdout,
        stderr=stderr_raw,
        exit_code=exit_code,
        success=success,
        generated_files=tuple(generated),
        error=error_text if not success else "",
    )
