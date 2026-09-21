"""Kind-agnostic path algebra for execution planes.

One concept: turn a raw path into a canonical path on a plane's OS, and
answer containment questions about it. Pure functions, no policy and no I/O.
Authorization lives in ``runtime_plane.access``; ambient plane bindings live
in ``runtime_plane.bindings``.

Machine ``PlaneRef.outputs_dir`` is ``outputs_under(root)``.
Sandbox guest disks use ``GuestLayout``, not these helpers.
"""

from __future__ import annotations

import ntpath
import os
from collections.abc import Sequence
from pathlib import PurePosixPath, PureWindowsPath

from lca.contracts.models.core.state.guest_layout import join_under, outputs_under
from lca.contracts.models.core.state.plane import PlaneRef

_WINDOWS_PLATFORMS = frozenset({"win32", "windows", "cygwin"})
_POSIX_TEMP_PREFIXES = ("/tmp", "/var/tmp")  # noqa: S108 — OS temp prefixes, not file creation


def is_windows(platform: str) -> bool:
    return (platform or "").lower() in _WINDOWS_PLATFORMS


def normalize(path: str, platform: str) -> str:
    """Collapse ``.`` and ``..`` using the platform's own separator rules.

    ``PureWindowsPath`` keeps ``..`` segments because pathlib will not resolve
    them without a filesystem, so containment checks would treat
    ``root\\..\\secret`` as inside ``root``. ``ntpath.normpath`` collapses them,
    matching ``os.path.normpath`` on the POSIX side.
    """
    if is_windows(platform):
        return ntpath.normpath(path)
    return os.path.normpath(path)


def is_absolute(path: str, platform: str) -> bool:
    if is_windows(platform):
        return PureWindowsPath(path).is_absolute()
    return path.startswith("/")


def resolve_plane_path(raw: str, plane: PlaneRef) -> str:
    """Relative → ``plane.root``. Absolute kept as-is. No remap."""
    text = (raw or "").strip() or "."
    if text in {".", "./"}:
        return normalize(plane.root, plane.platform)
    if is_absolute(text, plane.platform):
        return normalize(text, plane.platform)
    root = plane.root.rstrip("/\\")
    trimmed = text[2:] if text.startswith("./") else text
    sep = "\\" if is_windows(plane.platform) else "/"
    return normalize(f"{root}{sep}{trimmed}", plane.platform)


def is_within(path: str, root: str, platform: str) -> bool:
    """True when ``path`` is ``root`` itself or sits under it.

    Both sides are normalized first, so a ``..`` segment cannot fake
    containment. Windows comparison is case-insensitive, matching the OS.
    """
    if not root:
        return False
    target = normalize(path, platform)
    base = normalize(root, platform)
    if is_windows(platform):
        win_target: PureWindowsPath | PurePosixPath = PureWindowsPath(target)
        win_base: PureWindowsPath | PurePosixPath = PureWindowsPath(base)
        return win_target == win_base or win_base in win_target.parents
    posix_target = PurePosixPath(target)
    posix_base = PurePosixPath(base.rstrip("/") or "/")
    return posix_target == posix_base or posix_base in posix_target.parents


def is_temp_path(path: str, platform: str) -> bool:
    normalized = normalize(path, platform)
    if is_windows(platform):
        lowered = normalized.replace("/", "\\").lower()
        return "\\temp\\" in lowered or lowered.endswith("\\temp")
    return any(
        normalized == prefix or normalized.startswith(prefix + "/")
        for prefix in _POSIX_TEMP_PREFIXES
    )


def within_any(path: str, roots: Sequence[str], platform: str) -> bool:
    return any(is_within(path, root, platform) for root in roots if root)


__all__ = [
    "is_absolute",
    "is_temp_path",
    "is_windows",
    "is_within",
    "join_under",
    "normalize",
    "outputs_under",
    "resolve_plane_path",
    "within_any",
]
