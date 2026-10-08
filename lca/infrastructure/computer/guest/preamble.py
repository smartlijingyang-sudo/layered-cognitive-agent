"""Static guest prelude — load JSON args, resolve paths, emit a result.

No user values are interpolated here. Constants are host-side only.
"""

from __future__ import annotations

from lca.infrastructure.sandbox.factory.factory import ONLYBOXES

_SCRIPT_HELPERS = """
_DISPLAY_PATH_KEYS = ("path", "paths", "directoryPath", "directory", "directory_path", "file", "target")

def _display_path_value(value):
    if value == ROOT:
        return "."
    if value.startswith(ROOT + "/"):
        return value[len(ROOT) + 1:]
    return value

def _display_paths(node):
    if isinstance(node, dict):
        return {
            key: (
                _display_path_value(val)
                if key in _DISPLAY_PATH_KEYS and isinstance(val, str)
                else _display_paths(val)
            )
            for key, val in node.items()
        }
    if isinstance(node, list):
        return [_display_paths(item) for item in node]
    return node

def load_args(encoded):
    return json.loads(base64.b64decode(encoded).decode())

def resolve(path):
    p = Path(path or ROOT)
    s = str(p)
    if p.is_absolute() and GUEST_ROOT != ROOT and (s == GUEST_ROOT or s.startswith(GUEST_ROOT + "/")):
        # Contract-absolute input on a plane whose effective root differs
        # (Local sessions): map into ROOT instead of touching the host path.
        rel = s[len(GUEST_ROOT) + 1:]
        p = Path(ROOT) / rel if rel else Path(ROOT)
    elif not p.is_absolute():
        p = Path(ROOT) / p
    try:
        return p.resolve()
    except OSError:
        return p

def emit(value):
    # Single model-visible projection point: every guest script exits through
    # emit, so structured path fields reach the model workspace-relative on
    # every plane, while receipts keep the raw guest stdout as the fact.
    print(json.dumps(_display_paths(value), ensure_ascii=False), flush=True)
"""

SCRIPT_PRELUDE = (
    f"""
import base64
import fnmatch
import glob
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# The Local adapter exports LCA_GUEST_ROOT per session so host-side execution
# honors the guest contract with a per-run root. Onlyboxes containers leave it
# unset and keep the image contract root.
GUEST_ROOT = {ONLYBOXES.root!r}
ROOT = os.environ.get("LCA_GUEST_ROOT") or GUEST_ROOT
BG_DIR = str(Path(ROOT) / ".lca" / "background")
"""
    + _SCRIPT_HELPERS
)
