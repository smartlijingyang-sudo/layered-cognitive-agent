"""1:1 port of ``@deepseek-ai/dsh-session/json``.

Lossless-JSON validation and detached snapshots for durable session data.
"""

from __future__ import annotations

import math
from typing import Any

# ---------------------------------------------------------------------------
# Public type alias
# ---------------------------------------------------------------------------

JsonValue = (
    None
    | bool
    | int
    | float
    | str
    | list["JsonValue"]
    | dict[str, "JsonValue"]
)
"""A value that round-trips losslessly through JSON."""

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_plain_dict(value: object) -> bool:
    """Whether *value* is a plain dict (not a subclass)."""
    return type(value) is dict


# ---------------------------------------------------------------------------
# Iterative walk
# ---------------------------------------------------------------------------

_SENTINEL = object()


def _walk_json_value(value: Any, detach: bool) -> Any:
    """Validate lossless JSON iteratively, optionally materializing a detached
    snapshot.

    Returns the detached root when *detach* is True, ``True`` on success
    when *detach* is False, or ``None`` on rejection.
    """

    ancestors: set[int] = set()
    root_holder: list[Any] = [_SENTINEL]

    # Each task: (kind, ...)
    #   ("visit", value, dest_kind, dest_container, dest_key_or_index)
    #   ("array_item", source_list, index, dest_container_or_None)
    #   ("object_property", source_dict, key, dest_container_or_None)
    #   ("leave", id_of_container)
    tasks: list[tuple] = [
        ("visit", value, "root", None, None),
    ]

    while tasks:
        task = tasks.pop()
        kind = task[0]

        if kind == "leave":
            ancestors.discard(task[1])
            continue

        if kind == "array_item":
            _kind, source, idx, target = task
            if idx >= len(source):
                return None
            tasks.append(("visit", source[idx], "array", target, idx))
            continue

        if kind == "object_property":
            _kind, source, key, target = task
            tasks.append(("visit", source[key], "object", target, key))
            continue

        # kind == "visit"
        current = task[1]
        dest_kind = task[2]
        dest_target = task[3]
        dest_idx = task[4]

        if current is None:
            _assign_to(dest_kind, dest_target, dest_idx, None, root_holder)
            continue

        if isinstance(current, bool):
            _assign_to(dest_kind, dest_target, dest_idx, current, root_holder)
            continue

        if isinstance(current, str):
            _assign_to(dest_kind, dest_target, dest_idx, current, root_holder)
            continue

        if isinstance(current, (int, float)):
            if isinstance(current, float):
                if math.isnan(current) or math.isinf(current):
                    return None
                if current == 0.0 and math.copysign(1.0, current) < 0:
                    return None
            _assign_to(dest_kind, dest_target, dest_idx, current, root_holder)
            continue

        if not isinstance(current, (dict, list)):
            return None

        obj_id = id(current)
        if obj_id in ancestors:
            return None

        if isinstance(current, list):
            if type(current) is not list:
                return None
            length = len(current)
            target: Any = [None] * length if detach else None
            if target is not None:
                _assign_to(dest_kind, dest_target, dest_idx, target, root_holder)
            ancestors.add(obj_id)
            tasks.append(("leave", obj_id))
            for index in range(length - 1, -1, -1):
                tasks.append(("array_item", current, index, target))
            continue

        # dict
        if not _is_plain_dict(current):
            return None
        keys = list(current.keys())
        for k in keys:
            if not isinstance(k, str):
                return None
        obj_target: Any = {} if detach else None
        if obj_target is not None:
            _assign_to(dest_kind, dest_target, dest_idx, obj_target, root_holder)
        ancestors.add(obj_id)
        tasks.append(("leave", obj_id))
        for index in range(len(keys) - 1, -1, -1):
            key = keys[index]
            tasks.append(("object_property", current, key, obj_target))

    if detach:
        return root_holder[0]
    return True


def _assign_to(
    dest_kind: str,
    dest_target: Any,
    dest_idx: Any,
    item: Any,
    root_holder: list[Any],
) -> None:
    if dest_kind == "root":
        root_holder[0] = item
    elif dest_kind in ("array", "object"):
        if dest_target is not None:
            dest_target[dest_idx] = item


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def snapshot_json_value(value: Any) -> JsonValue | None:  # type: ignore[valid-type]
    """Validate and detach lossless JSON in one read per property.

    Returns the detached snapshot, or ``None`` when the value is not
    losslessly JSON-serializable.
    """
    result = _walk_json_value(value, True)
    if result is None or result is True:
        return None
    return result


def is_json_value(value: Any) -> bool:
    """Test the same lossless JSON boundary as :func:`snapshot_json_value`
    without detaching it."""
    return _walk_json_value(value, False) is True
