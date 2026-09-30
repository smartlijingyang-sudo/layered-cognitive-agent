"""Unified diffs for standing-file changes.

The watcher supplies the previous and current text. This module only formats
the difference a model can read.
"""

from __future__ import annotations

import difflib
from collections.abc import Sequence


def unified_diff(path: str, before: str, after: str) -> str:
    """Return a unified diff, or an empty string when the texts match."""

    if before == after:
        return ""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=path,
        tofile=path,
        n=2,
    )
    return "".join(lines)


def render_standing_diff(changes: Sequence[tuple[str, str]]) -> str:
    """Render non-empty diffs as one note. ``changes`` is ``(path, diff)``."""

    visible = [(path, diff) for path, diff in changes if diff.strip()]
    if not visible:
        return ""
    parts = ["常驻文件有更新。以下是相对上一份副本的差异。"]
    for _path, diff in visible:
        parts.append(diff.rstrip())
    return "\n".join(parts)


__all__ = ["render_standing_diff", "unified_diff"]
