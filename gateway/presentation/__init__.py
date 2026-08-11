"""Presentation plane — structured turn-based representation of agent runs.

Value types and state machines for transforming journal events into
a coherent narrative that maps directly to LobeHub's UI model.

Design:
    - Frozen dataclasses (value semantics)
    - Explicit state machines (no ad-hoc flag tracking)
    - Single source of truth (TurnSnapshot)
    - Strategy Registry for tool state builders
    - Centralized artifact URL resolution
"""

from gateway.presentation.artifact_registry import (
    Artifact,
    ArtifactRegistry,
    absolutize_file_parts,
    absolutize_url,
    gateway_public_base,
)
from gateway.presentation.tool_lifecycle import (
    InvalidTransitionError,
    ToolLifecycleMap,
)
from gateway.presentation.tool_state_builders import (
    ToolStateBuilder,
    build_state_from_invoked,
    build_tool_plugin_state,
    get_tool_state_builder,
    register_tool_state_builder,
)
from gateway.presentation.turn_snapshot import (
    PhaseKind,
    ToolLifecycleState,
    ToolPhase,
    Turn,
    TurnSnapshot,
)
from gateway.presentation.turn_state_machine import TurnStateMachine

__all__ = [
    "Artifact",
    "ArtifactRegistry",
    "InvalidTransitionError",
    "PhaseKind",
    "ToolLifecycleMap",
    "ToolLifecycleState",
    "ToolPhase",
    "ToolStateBuilder",
    "Turn",
    "TurnSnapshot",
    "TurnStateMachine",
    "absolutize_file_parts",
    "absolutize_url",
    "build_state_from_invoked",
    "build_tool_plugin_state",
    "gateway_public_base",
    "get_tool_state_builder",
    "register_tool_state_builder",
]
