"""Onlyboxes shared constants, code bootstrap, and response parsing.

Extracted from ``onlyboxes_adapter`` to keep bootstrap logic, parsing,
and constants in a single shared module.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import httpx

from lca.contracts.models.core.sandbox import SandboxResult
from lca.layer0_infra.credentials.sandbox_env import build_sandbox_env_preamble
from lca.layer0_infra.sandbox.onlyboxes_artifacts import strip_artifacts
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

# ── constants ───────────────────────────────────────────────────────

PYTHON_LANGUAGES: frozenset[str] = frozenset({"python", "py"})
CAPABILITY_PYTHON = "pythonExec"
CAPABILITY_TERMINAL = "terminalExec"
TASK_MODE_SYNC = "sync"
MAX_WAIT_MS = 120_000
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


def build_minimal_bootstrap(code: str) -> str:
    """Minimal bootstrap — no file embedding (files are pre-staged via write_files).

    Provides: env preamble, numpy/pandas JSON patch, matplotlib warning
    suppression, and ``exec`` of user code.
    """
    env_preamble = build_sandbox_env_preamble()
    code_literal = json.dumps(_strip_surrogates(code))
    return f"""# --- LCA minimal bootstrap ---
import os as _lca_os, sys as _lca_sys, json as _lca_json
{env_preamble}
# numpy/pandas JSON patch
_lca_original_dumps = _lca_json.dumps
def _lca_numpy_dumps(obj, *args, **kwargs):
    def _numpy_default(o):
        if hasattr(o, "item"): return o.item()
        raise TypeError(f"Object of type {{type(o).__name__}} is not JSON serializable")
    kwargs.setdefault("default", _numpy_default)
    return _lca_original_dumps(obj, *args, **kwargs)
_lca_json.dumps = _lca_numpy_dumps

import warnings as _lca_warnings
_lca_warnings.filterwarnings("ignore", module="matplotlib.font_manager")

try:
    exec(compile({code_literal}, "<lca-user>", "exec"), {{"__name__": "__main__"}})
except SystemExit as _lca_se:
    if _lca_se.code not in (0, None):
        raise
"""


def parse_terminal_response(
    response: httpx.Response,
    emitter: SandboxStreamEmitter,
) -> SandboxResult:
    """Parse ``POST /api/v1/commands/terminal`` response.

    Expected JSON shape: ``{"exit_code": int, "stdout": str,
    "stderr": str, "session_id": str}``.
    """
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

    if response.status_code >= 400:
        message = str(payload.get("error") or f"HTTP {response.status_code}")
        emitter.emit_stderr(message + "\n")
        return SandboxResult(success=False, exit_code=1, error=message, stderr=message + "\n")

    try:
        exit_code = int(payload.get("exit_code", 0))
    except (TypeError, ValueError):
        exit_code = 1

    stdout = str(payload.get("stdout") or "")
    stderr = str(payload.get("stderr") or "")

    # ADR-0046 alignment: harvest artifact marker block from stdout
    cleaned_stdout, generated, diags = strip_artifacts(stdout)
    if diags:
        stderr = stderr + "".join(diags)

    if cleaned_stdout:
        emitter.emit_stdout(cleaned_stdout)
    if stderr:
        emitter.emit_stderr(stderr)

    success = exit_code == 0
    error_text = "" if success else (stderr.strip() or f"exit_code={exit_code}")
    return SandboxResult(
        stdout=cleaned_stdout,
        stderr=stderr,
        exit_code=exit_code,
        success=success,
        error=error_text,
        generated_files=tuple(generated),
    )
