"""Field merge strategies for observability fold (ADR-0198)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any, cast

from lca.contracts.observability.compile.plan import MergeStrategy


def _richness(value: Any) -> int:
    """Heuristic richness score for merge decisions."""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.strip())
    if isinstance(value, Mapping):
        return sum(_richness(v) for v in value.values()) + len(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return sum(_richness(v) for v in value) + len(value)
    if isinstance(value, bool):
        return 1
    if isinstance(value, (int, float)):
        return 1 if value else 0
    return 1


def record_richness(record: Any) -> int:
    """Sum richness across dataclass fields or mapping keys."""
    if record is None:
        return 0
    if is_dataclass(record):
        total = 0
        for f in fields(record):
            total += _richness(getattr(record, f.name))
        return total
    if isinstance(record, Mapping):
        return sum(_richness(v) for v in record.values())
    return _richness(record)


def _is_empty_scalar(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, Mapping):
        return len(value) == 0
    if isinstance(value, (list, tuple, set, frozenset)):
        return len(value) == 0
    return False


def merge_dataclass(existing: Any | None, incoming: Any, strategy: MergeStrategy) -> Any:
    """Merge two dataclass instances of the same type per configured strategy."""
    if existing is None:
        return incoming
    if not is_dataclass(existing) or not is_dataclass(incoming):
        raise TypeError("merge_dataclass requires dataclass instances")
    if type(existing) is not type(incoming):
        return incoming

    if strategy == "deny_overwrite":
        return existing

    if strategy == "replace":
        return incoming

    if strategy == "replace_richer":
        if record_richness(incoming) >= record_richness(existing):
            return incoming
        return existing

    if strategy == "fill_empty_only":
        updates: dict[str, Any] = {}
        for f in fields(existing):
            cur = getattr(existing, f.name)
            new = getattr(incoming, f.name)
            if _is_empty_scalar(cur) and not _is_empty_scalar(new):
                updates[f.name] = new
        if not updates:
            return existing
        merged_dict = {f.name: updates.get(f.name, getattr(existing, f.name)) for f in fields(existing)}
        new_obj = type(existing)(**merged_dict)  # type: ignore[misc]
        return cast("Any", new_obj)

    raise ValueError(f"unknown merge strategy {strategy!r}")


__all__ = ["merge_dataclass", "record_richness"]
