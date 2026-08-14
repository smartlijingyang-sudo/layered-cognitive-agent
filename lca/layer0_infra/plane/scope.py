"""Run-scoped bindings + machine path audit (pathScopeAudit)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import PurePosixPath, PureWindowsPath

from lca.contracts.models.core.plane import PlaneBindings, PlaneKind, PlaneRef
from lca.contracts.models.core.result import ApprovalPendingError

_bindings: ContextVar[PlaneBindings | None] = ContextVar("plane_bindings", default=None)

_POSIX_TEMP = ("/tmp", "/var/tmp")  # noqa: S108 — OS temp prefixes, not file creation


@contextmanager
def plane_bindings_scope(bindings: PlaneBindings) -> Iterator[PlaneBindings]:
    token = _bindings.set(bindings)
    try:
        yield bindings
    finally:
        _bindings.reset(token)


def current_bindings() -> PlaneBindings | None:
    return _bindings.get()


def current_primary() -> PlaneRef | None:
    bound = _bindings.get()
    return None if bound is None else bound.primary


def resolve_plane_path(raw: str, plane: PlaneRef) -> str:
    """Relative → plane.root. Absolute kept as-is. Collapse ``..``. No remap."""
    text = (raw or "").strip() or "."
    if text in {".", "./"}:
        return _normalize(plane.root, plane.platform)
    if _is_absolute(text, plane.platform):
        return _normalize(text, plane.platform)
    root = plane.root.rstrip("/\\")
    trimmed = text[2:] if text.startswith("./") else text
    sep = "\\" if _windows(plane.platform) else "/"
    return _normalize(f"{root}{sep}{trimmed}", plane.platform)


def path_needs_approval(path: str, plane: PlaneRef) -> bool:
    if plane.kind is not PlaneKind.MACHINE:
        return False
    resolved = resolve_plane_path(path, plane)
    if _inside(resolved, plane.root, plane.platform):
        return False
    return not _is_temp(resolved, plane.platform)


def raise_if_out_of_scope(path: str, plane: PlaneRef) -> str:
    resolved = resolve_plane_path(path, plane)
    if path_needs_approval(resolved, plane):
        raise ApprovalPendingError(
            {
                "type": "path_scope",
                "path": resolved,
                "root": plane.root,
                "risk_reason": f"path {resolved} is outside machine root {plane.root}",
            }
        )
    return resolved


def _normalize(path: str, platform: str) -> str:
    if _windows(platform):
        return str(PureWindowsPath(path))
    return os.path.normpath(path)


def _windows(platform: str) -> bool:
    return platform.lower() in {"win32", "windows", "cygwin"}


def _is_absolute(path: str, platform: str) -> bool:
    if _windows(platform):
        return PureWindowsPath(path).is_absolute()
    return path.startswith("/")


def _inside(path: str, root: str, platform: str) -> bool:
    path = _normalize(path, platform)
    root = _normalize(root, platform)
    if _windows(platform):
        target = PureWindowsPath(path)
        base = PureWindowsPath(root)
        return target == base or base in target.parents
    target = PurePosixPath(path)
    base = PurePosixPath(root.rstrip("/") or "/")
    return target == base or base in target.parents


def _is_temp(path: str, platform: str) -> bool:
    path = _normalize(path, platform)
    if _windows(platform):
        lowered = path.replace("/", "\\").lower()
        return "\\temp\\" in lowered or lowered.endswith("\\temp")
    return any(path == prefix or path.startswith(prefix + "/") for prefix in _POSIX_TEMP)
