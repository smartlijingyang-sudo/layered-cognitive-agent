"""Onlyboxes session-mode guest bootstrap — pickle state + idempotent mounts (ADR-0050)."""

from __future__ import annotations

import base64
import json

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT
from lca.layer0_infra.sandbox.onlyboxes_artifacts import ARTIFACT_BEGIN, ARTIFACT_END
from lca.layer0_infra.sandbox.output_collect import sandbox_output_dir


def safe_rel_name(name: str) -> str:
    """Strip path traversal; keep basename for guest mount."""
    cleaned = name.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ".."}]
    return parts[-1] if parts else "file.bin"


def _strip_surrogates(text: str) -> str:
    return "".join("\ufffd" if "\ud800" <= ch <= "\udfff" else ch for ch in text)


def build_session_wrapped_code(code: str, files: dict[str, bytes] | None) -> str:
    """Session bootstrap: idempotent mounts + pickle state + harvest."""
    mount_items: list[tuple[str, str]] = []
    for raw_name, data in (files or {}).items():
        name = safe_rel_name(raw_name)
        mount_items.append((name, base64.b64encode(data).decode("ascii")))

    mounts_literal = json.dumps(mount_items, ensure_ascii=False)
    out_dir = sandbox_output_dir()
    user_literal = json.dumps(_strip_surrogates(code))
    state_path = "/tmp/.lca_state.pkl"  # noqa: S108 — guest-only pickle path

    return f"""# --- LCA Onlyboxes session bootstrap (do not edit) ---
import base64 as _lca_b64
import json as _lca_json
import os as _lca_os
import pickle as _lca_pickle
import traceback as _lca_tb
from pathlib import Path as _lca_Path

_LCA_MOUNT = {SANDBOX_MOUNT_ROOT!r}
_LCA_OUT = {out_dir!r}
_LCA_STATE = {state_path!r}
_LCA_MOUNTS = {mounts_literal}
_LCA_USER_CODE = {user_literal}
_lca_os.makedirs(_LCA_MOUNT, exist_ok=True)
_lca_os.makedirs(_LCA_OUT, exist_ok=True)
for _lca_name, _lca_b64s in _LCA_MOUNTS:
    _lca_path = _lca_Path(_LCA_MOUNT) / _lca_name
    _lca_path.write_bytes(_lca_b64.b64decode(_lca_b64s))

_lca_original_dumps = _lca_json.dumps
def _lca_numpy_dumps(obj, *args, **kwargs):
    def _numpy_default(o):
        if hasattr(o, "item"):
            return o.item()
        raise TypeError(f"Object of type {{type(o).__name__}} is not JSON serializable")
    kwargs.setdefault("default", _numpy_default)
    return _lca_original_dumps(obj, *args, **kwargs)
_lca_json.dumps = _lca_numpy_dumps

import warnings as _lca_warnings
_lca_warnings.filterwarnings("ignore", module="matplotlib.font_manager")

_lca_ns = {{"__name__": "__main__"}}
try:
    with open(_LCA_STATE, "rb") as _lca_sf:
        _lca_ns.update(_lca_pickle.load(_lca_sf))
except (FileNotFoundError, Exception):
    pass

_lca_user_failed = False
try:
    exec(compile(_LCA_USER_CODE, "<lca-user>", "exec"), _lca_ns)
except SystemExit as _lca_se:
    if _lca_se.code not in (0, None):
        _lca_user_failed = True
except Exception:
    _lca_user_failed = True
    _lca_tb.print_exc()

_lca_skip = {{'__name__', '__builtins__'}}
_lca_save = {{}}
for _lca_k, _lca_v in _lca_ns.items():
    if _lca_k.startswith('_') or _lca_k in _lca_skip:
        continue
    try:
        _lca_pickle.dumps(_lca_v)
        _lca_save[_lca_k] = _lca_v
    except Exception:
        pass
try:
    with open(_LCA_STATE, "wb") as _lca_sf:
        _lca_pickle.dump(_lca_save, _lca_sf)
except Exception:
    pass

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
