"""Single canonical implementation for the arguments human-readable summary.

Consolidates the two prior private copies
(``safe_executor._summarize_args_for_cursor`` and
``tool_journal._summarize_args``) so the producer side has one truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def summarize_args(args: Mapping[str, Any], *, limit: int = 200) -> str:
    """Render a one-line human-readable summary of ``args``.

    Produces the value carried by ``step.tool_call.arguments_summary``.
    Format: ``"key1=repr(v1)[:32], key2=..., ..."`` — up to five keys,
    each value reprised and truncated to 32 chars. Total length bounded
    by ``limit`` (default 200) plus a trailing ellipsis.
    """
    if not args:
        return ""
    keys = list(args.keys())[:5]
    head = ", ".join(f"{k}={repr(args[k])[:32]}" for k in keys)
    if len(head) > limit:
        return head[:limit] + "…"
    return head


__all__ = ["summarize_args"]
