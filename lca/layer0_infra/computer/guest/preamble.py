"""Guest script preamble — shared sandbox-side helpers."""

from __future__ import annotations

from lca.layer0_infra.computer.constants import (
    BACKGROUND_CMD_DIR,
    COMPUTER_RESULT_BEGIN,
    COMPUTER_RESULT_END,
    COMPUTER_WORKSPACE_ROOT,
)

_GUEST_PREAMBLE = f"""
import json as _j
import os as _o
import re as _re
import glob as _glob
import fnmatch as _fn
import shutil as _sh
import subprocess as _sp
import sys as _sys
from pathlib import Path as _P
from datetime import datetime as _dt

_ROOT = {COMPUTER_WORKSPACE_ROOT!r}
_BG_DIR = {BACKGROUND_CMD_DIR!r}

def _resolve(path: str) -> _P:
    p = _P(path)
    if not p.is_absolute():
        p = _P(_ROOT) / p
    try:
        return p.resolve()
    except OSError:
        return p

def _emit(result: dict):
    print({COMPUTER_RESULT_BEGIN!r} + _j.dumps(result, ensure_ascii=False) + {COMPUTER_RESULT_END!r}, flush=True)
"""


def wrap_guest_body(body: str) -> str:
    """Wrap guest logic that must assign ``result`` dict."""
    return _GUEST_PREAMBLE + "\n" + body.strip() + "\n\n_emit(result)\n"
