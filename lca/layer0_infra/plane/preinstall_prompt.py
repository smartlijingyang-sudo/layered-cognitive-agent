"""Render ``{{preinstalled}}`` from YAML notes + catalog tuples.

Inventory (what is installed) lives in contracts.
How to use it lives in ``prompts/preinstall.yaml``.
"""

from __future__ import annotations

from functools import cache
from typing import Any

import yaml

from lca.contracts.models.core.plane import PlaneKind
from lca.contracts.models.core.sandbox import (
    SANDBOX_PREINSTALLED_CLI_TOOLS,
    SANDBOX_PREINSTALLED_PYTHON_PACKAGES,
)
from lca.layer0_infra.plane.prompts import load_plane_data

_PLANE_KEY = {
    PlaneKind.MACHINE: "machine",
    PlaneKind.SANDBOX: "sandbox",
}


@cache
def _catalog() -> dict[str, Any]:
    raw = yaml.safe_load(load_plane_data("preinstall.yaml")) or {}
    if not isinstance(raw, dict):
        msg = "preinstall.yaml must be a mapping"
        raise TypeError(msg)
    return raw


def render_preinstalled_block(*, plane: PlaneKind) -> str:
    data = _catalog()
    key = _PLANE_KEY.get(plane, "sandbox")
    planes = data.get("planes") if isinstance(data.get("planes"), dict) else {}
    spec = planes.get(key) if isinstance(planes, dict) else None
    if not isinstance(spec, dict):
        spec = {}
    header = str(spec.get("header") or "Pre-installed software")
    notes: list[str] = []
    shared = data.get("shared") if isinstance(data.get("shared"), dict) else {}
    for block in (shared, spec):
        raw_notes = block.get("notes") if isinstance(block, dict) else None
        if isinstance(raw_notes, list):
            notes.extend(str(item).strip() for item in raw_notes if str(item).strip())
    packages = ", ".join(SANDBOX_PREINSTALLED_PYTHON_PACKAGES)
    tools = ", ".join(SANDBOX_PREINSTALLED_CLI_TOOLS)
    lines = [
        f"**{header}**",
        f"- Python packages (pip/venv): {packages}",
        f"- CLI tools: {tools}",
        *(f"- {note}" for note in notes),
    ]
    return "\n".join(lines)
