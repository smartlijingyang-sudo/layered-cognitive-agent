"""Compose a guest computer op the way native LobeHub Onlyboxes does.

LobeHub ``OnlyboxesSandboxProvider.runJsonScript`` keeps a *static* Python
program and passes arguments as ``json.loads(base64.b64decode(...))``.
Params never become Python source. ``None`` / ``True`` / ``False`` stay JSON.

The only host-side interpolation is a base64 alphabet string — always a
valid Python literal.
"""

from __future__ import annotations

import base64
import json
from typing import Any


def encode_params(params: dict[str, Any]) -> str:
    raw = json.dumps(params, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def compose_json_script(script: str, params: dict[str, Any]) -> str:
    """``script`` must define ``main(encoded)``. Host only appends the call."""
    return f"{script.rstrip()}\n\nmain({encode_params(params)!r})\n"
