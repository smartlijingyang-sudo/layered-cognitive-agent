"""Tool invocation scope package (INV-ARCH-18)."""

from __future__ import annotations

from lca.infrastructure.tools.tool.invocation_scope import (
    get_current_tool_invocation_id,
    tool_invocation_scope,
)

__all__ = [
    "get_current_tool_invocation_id",
    "tool_invocation_scope",
]
