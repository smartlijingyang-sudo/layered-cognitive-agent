"""Collect user-visible delivery material from folded control turns (ADR-0196)."""

from __future__ import annotations

from dataclasses import dataclass

from lca.cognition.convergence.payload import (
    merge_files_created,
    payload_stdout,
    turn_has_delivery_signal,
)
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.perceive.projection import current_manifest_from_state
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.context.turn_control_reader import control_turns


@dataclass(frozen=True, slots=True)
class DeliveryMaterial:
    """Folded view of the best producer output available for user delivery."""

    stdout: str
    files_created: tuple[str, ...]
    artifact_lines: tuple[str, ...]


def artifacts_from_manifest(state: AgentState) -> tuple[str, ...]:
    manifest = current_manifest_from_state(state)
    if manifest is None:
        return ()
    lines: list[str] = []
    for item in manifest.items:
        if item.kind != "workspace_artifacts" or not isinstance(item.payload, list):
            continue
        for art in item.payload:
            if not isinstance(art, dict):
                continue
            path = str(art.get("path") or "").strip()
            url = str(art.get("url") or "").strip()
            if path and url:
                lines.append(f"- {path} ({url})")
            elif path:
                lines.append(f"- {path}")
    return tuple(lines)


def artifact_count(state: AgentState) -> int:
    manifest = current_manifest_from_state(state)
    if manifest is None:
        return 0
    for item in manifest.items:
        if item.kind == "workspace_artifacts" and isinstance(item.payload, list):
            return len([a for a in item.payload if isinstance(a, dict)])
    return 0


def _is_use_tool(action_type: object) -> bool:
    return action_type == ActionType.USE_TOOL or action_type == "use_tool"


def collect_delivery_material(state: AgentState) -> DeliveryMaterial:
    best_stdout = ""
    best_files: tuple[str, ...] = ()
    for turn in reversed(control_turns(state)):
        if not _is_use_tool(turn.action_type):
            continue
        if not turn.observation_success:
            continue
        stdout = payload_stdout(turn.observation_payload)
        files = merge_files_created(
            turn.observation_payload,
            files_created=turn.files_created,
        )
        if turn_has_delivery_signal(
            turn.observation_payload,
            files_created=turn.files_created,
            task=state.task or "",
        ):
            best_stdout = stdout
            best_files = files
            break
    return DeliveryMaterial(
        stdout=best_stdout,
        files_created=best_files,
        artifact_lines=artifacts_from_manifest(state),
    )


__all__ = [
    "DeliveryMaterial",
    "artifact_count",
    "artifacts_from_manifest",
    "collect_delivery_material",
]
