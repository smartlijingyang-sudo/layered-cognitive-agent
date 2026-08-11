"""Shared helpers for LCA → LobeHub tool wire format translation.

Backward-compatible re-export — all logic moved to ``lobehub_adapter/json_helpers.py``
and ``lobehub_adapter/build_state.py``.
"""

from __future__ import annotations

from gateway.lobehub_bridge.lobehub_adapter.build_state import (
    add_error_field,
    merge_success_state,
)
from gateway.lobehub_bridge.lobehub_adapter.json_helpers import (
    copy_fields,
    first_str,
    first_str_as_list,
    parse_args_json,
    safe_json_string,
)

__all__ = [
    "add_error_field",
    "copy_fields",
    "first_str",
    "first_str_as_list",
    "merge_success_state",
    "parse_args_json",
    "safe_json_string",
]
