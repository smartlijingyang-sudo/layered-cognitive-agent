"""Static guest prelude — load JSON args, resolve paths, emit a result.

No user values are interpolated here. Constants are host-side only.
"""

from __future__ import annotations

from lca.layer0_infra.computer.constants import (
    BACKGROUND_CMD_DIR,
    COMPUTER_WORKSPACE_ROOT,
)

SCRIPT_PRELUDE = f"""
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

ROOT = {COMPUTER_WORKSPACE_ROOT!r}
BG_DIR = {BACKGROUND_CMD_DIR!r}

def load_args(encoded):
    return json.loads(base64.b64decode(encoded).decode())

def resolve(path):
    p = Path(path or ROOT)
    if not p.is_absolute():
        p = Path(ROOT) / p
    try:
        return p.resolve()
    except OSError:
        return p

def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)
"""
