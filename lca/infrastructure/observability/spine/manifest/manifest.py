"""Execution-point whitelist — COMPAT re-export (ADR-0195 O1 / P2-17).

SSOT for production EP registration:
``lca_kernel/events/config/observability/spine.yaml`` (+ business yaml)
→ ``lca_kernel.events.payloads_spine.SPINE_EXECUTION_POINTS``.

Loads ``payloads_spine`` via ``importlib`` (not ``lca_kernel.events`` package
``__init__``) to avoid import cycle:
``event_record`` → ``manifest`` → ``payloads_spine`` → ``events.persistence``
→ ``infrastructure.observability`` → ``event_record``.

# COMPAT(owner: ADR-0195 O1 / P1-18, from: manifest.py inline EXECUTION_POINTS tuple,
# to: spine.yaml + SPINE_EXECUTION_POINTS,
# delete_when: rg "from lca.infrastructure.observability.spine.manifest.manifest import EXECUTION_POINTS" lca/ = 0,
# forbidden_new_usage: 禁止在本模块新增裸 EP 字符串或 inline tuple; 新 EP 只许改 yaml + payloads_spine)
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    EXECUTION_POINTS: tuple[str, ...]

def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    msg = "repository root (pyproject.toml) not found"
    raise RuntimeError(msg)


_REPO_ROOT = _repo_root()
_PAYLOADS_SPINE_PATH = _REPO_ROOT / "lca_kernel" / "events" / "payloads" / "spine.py"
_CACHED_EXECUTION_POINTS: tuple[str, ...] | None = None


def _load_spine_execution_points() -> tuple[str, ...]:
    spec = importlib.util.spec_from_file_location(
        "lca_kernel.events.payloads.spine",
        _PAYLOADS_SPINE_PATH,
    )
    if spec is None or spec.loader is None:
        msg = f"cannot load spine EP SSOT from {_PAYLOADS_SPINE_PATH}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    eps = module.SPINE_EXECUTION_POINTS
    if not isinstance(eps, tuple):
        msg = "SPINE_EXECUTION_POINTS must be a tuple"
        raise TypeError(msg)
    return eps


def __getattr__(name: str) -> tuple[str, ...]:
    if name == "EXECUTION_POINTS":
        global _CACHED_EXECUTION_POINTS
        if _CACHED_EXECUTION_POINTS is None:
            _CACHED_EXECUTION_POINTS = _load_spine_execution_points()
        return _CACHED_EXECUTION_POINTS
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = ["EXECUTION_POINTS"]
