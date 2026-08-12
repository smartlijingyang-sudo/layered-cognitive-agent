"""Presentation plane — structured turn-based representation of agent runs.

Value types and state machines for transforming journal events into
a coherent narrative that maps directly to LobeHub's UI model.

Design:
    - Frozen dataclasses (value semantics)
    - Explicit state machines (no ad-hoc flag tracking)
    - Single source of truth (TurnSnapshot)
    - Tool UI state production SSOT lives in layer1 ``tool_ui_state``;
      this package assembles snapshots and re-exports thin facades
    - Centralized artifact URL resolution
"""

from gateway.narrative.artifact_registry import (
    Artifact,
    ArtifactRegistry,
    absolutize_file_parts,
    absolutize_url,
    gateway_public_base,
)
from gateway.narrative.tool_lifecycle import (
    InvalidTransitionError,
    ToolLifecycleMap,
)
from gateway.narrative.tool_state_builders import (
    build_state_from_invoked,
    build_state_from_started,
    build_tool_plugin_state,
)
from gateway.narrative.turn_builder import TurnBuilder
from gateway.narrative.turn_model import (
    PhaseKind,
    ToolLifecycleState,
    ToolPhase,
    Turn,
    TurnSnapshot,
)

__all__ = [
    "Artifact",
    "ArtifactRegistry",
    "InvalidTransitionError",
    "PhaseKind",
    "ToolLifecycleMap",
    "ToolLifecycleState",
    "ToolPhase",
    "Turn",
    "TurnBuilder",
    "TurnSnapshot",
    "absolutize_file_parts",
    "absolutize_url",
    "build_state_from_invoked",
    "build_state_from_started",
    "build_tool_plugin_state",
    "gateway_public_base",
]
