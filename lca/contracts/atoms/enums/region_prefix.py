"""RegionPrefix — typed view of the ``lca/nodes/`` top-level directories.

ADR-0231 §Decision D1: the region SSOT is the file system. ``lca/nodes/<region>/``
is the canonical name; plugin ``provides=`` strings and bundle ``region:`` fields
must equal one of those directory names (no ``phase:`` / ``region:`` prefix).

This module exposes:
  - :class:`RegionPrefix` — a ``str`` enum mirroring the directory set
  - :func:`collect_region_prefixes` — reads ``lca/nodes/`` top-level entries
  - :exc:`UnknownRegionPrefixError` — raised when a string is not a known region

The enum is generated at import time so new region directories are picked up
without code changes; the snapshot test in
``tests/contracts/test_region_prefix.py`` guards against silent drift.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


_NODES_DIR = Path(__file__).resolve().parents[3] / "nodes"


class UnknownRegionPrefixError(ValueError):
    """Raised when a region string is not in the canonical ``lca/nodes/`` set."""

    def __init__(self, raw: object) -> None:
        super().__init__(
            f"unknown region prefix: {raw!r}; "
            f"must equal a top-level directory under lca/nodes/ "
            f"(see ADR-0231 D1)"
        )


def collect_region_prefixes() -> frozenset[str]:
    """Walk ``lca/nodes/`` and return its top-level directory names.

    Skips ``__pycache__`` and any non-directory entries. The returned frozenset
    is the canonical SSOT for the :class:`RegionPrefix` enum.
    """
    if not _NODES_DIR.is_dir():
        return frozenset()
    out: set[str] = set()
    for entry in _NODES_DIR.iterdir():
        if entry.name.startswith("__") or not entry.is_dir():
            continue
        if ":" in entry.name or "/" in entry.name:
            # Defensive: a directory name should never contain separators,
            # but reject so a misnamed directory does not silently appear
            # in the SSOT.
            continue
        out.add(entry.name)
    return frozenset(out)


def _build_region_prefix_enum() -> type[RegionPrefix]:
    """Materialize the :class:`RegionPrefix` enum from the live SSOT."""
    members: dict[str, str] = {}
    for name in sorted(collect_region_prefixes()):
        members[name.upper()] = name
    return Enum("RegionPrefix", members, type=str)  # type: ignore[misc]


# Re-declare RegionPrefix as a str Enum so ``RegionPrefix.THINK == "think"``.
# The enum class is rebuilt at import time from the file system.
class _RegionPrefix(str, Enum):
    """str Enum over ``lca/nodes/`` top-level directories (ADR-0231 D1)."""

    @classmethod
    def parse(cls, raw: object) -> "_RegionPrefix":
        """Strict parse — raises :exc:`UnknownRegionPrefixError` on miss."""
        if not isinstance(raw, str) or not raw.strip():
            raise UnknownRegionPrefixError(raw)
        candidate = raw.strip()
        try:
            return cls(candidate)
        except ValueError as exc:
            raise UnknownRegionPrefixError(raw) from exc

    @classmethod
    def contains(cls, raw: object) -> bool:
        """Non-throwing lookup — ``True`` iff ``raw`` is a canonical region."""
        if not isinstance(raw, str) or not raw:
            return False
        try:
            cls(raw)
        except ValueError:
            return False
        return True


# Replace the body with the live FS-derived members.
RegionPrefix = _RegionPrefix(  # type: ignore[assignment,misc]
    "RegionPrefix",
    {name.upper(): name for name in sorted(collect_region_prefixes())},
)


__all__ = [
    "RegionPrefix",
    "UnknownRegionPrefixError",
    "collect_region_prefixes",
]
