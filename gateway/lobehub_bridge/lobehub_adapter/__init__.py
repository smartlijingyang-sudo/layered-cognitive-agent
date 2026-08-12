"""LobeHub adapter — bridges LCA tool invocations to LobeHub's frontend protocol.

This package provides the translation layer between LCA's internal tool
representation and the wire format LobeHub's frontend expects for rendering
tool cards (Inspector title, Detail view, collapse behavior).

Public API:
    - ``resolve_tool_wire`` — look up the wire spec for an LCA tool name
    - ``wire_tool_name`` — build ``identifier____apiName`` wire format
    - ``split_wire_name`` — parse wire name back to (identifier, api_name)
    - ``transform_tool_arguments`` — adapt LCA args → LobeHub wire args
    - ``build_tool_plugin_state`` — build pluginState from LCA tool result
    - ``tool_result_content`` — extract display text from tool result
    - ``tool_result_preview_limit`` — per-tool preview length limit

Design patterns used:
    - Strategy (ArgsTransform / StateBuilder protocols)
    - Registry (TOOL_REGISTRY declarative mapping)
    - Builder (FieldMapper declarative arg transform construction)
    - Template Method (build_tool_plugin_state fixed pipeline)

Data flow:
    LCA tool call → resolve_tool_wire() → ToolWireSpec
                                        → transform_args(args) → wire args
                                        → build_state(result)  → pluginState
                                        → LobeHub frontend Tool card
"""

from __future__ import annotations

# ── Public API ──────────────────────────────────────────────
from gateway.lobehub_bridge.lobehub_adapter.tool_registry import (
    CLOUD_SANDBOX_WIRE,
    TOOL_REGISTRY,
    build_tool_plugin_state,
    resolve_tool_wire,
    tool_result_content,
    tool_result_preview_limit,
    transform_tool_arguments,
)
from gateway.lobehub_bridge.lobehub_adapter.tool_spec import (
    ToolWireSpec,
    split_wire_name,
    wire_tool_name,
)

__all__ = [
    "CLOUD_SANDBOX_WIRE",
    "TOOL_REGISTRY",
    "ToolWireSpec",
    "build_tool_plugin_state",
    "resolve_tool_wire",
    "split_wire_name",
    "tool_result_content",
    "tool_result_preview_limit",
    "transform_tool_arguments",
    "wire_tool_name",
]
