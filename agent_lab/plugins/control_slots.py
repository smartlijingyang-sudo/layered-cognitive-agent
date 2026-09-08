"""control_slots plugin — owns the control-slot insertion policy.

Reads the host spec's phase-tagged sub_specs and inserts sibling control
sub_specs per the wiring table below. The skeleton ``compile()`` only
fans ``before_compile``; this plugin owns which slots attach where.
Swap or omit the plugin to change / disable the policy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_lab.plugins.base import GraphPlugin, register_plugin

_log = logging.getLogger(__name__)

# Phase-name → list of (sub_spec_id, input_map, output_map) entries.
# Cross-cutting observers are listed under every phase they should attach to.
# input_map / output_map: parent_port → nested_port (input) and nested → parent (output).
_PHASE_OWNER_WIRING: dict[str, list[tuple[str, dict[str, str], dict[str, str]]]] = {
    "perceive": [
        ("perceive_context", {"user_turn": "in_args"}, {"allowed": "perceive_context_allowed"}),
        (
            "observe_checkpoint",
            {"in_event_log": "in_event_log"},
            {"checkpoint_event": "checkpoint_event"},
        ),
        ("observe_wildcard", {"in_event": "in_event"}, {"wildcard_event": "wildcard_event"}),
    ],
    "think": [
        ("think_guard", {"decision_out": "in_decision"}, {"out_decision": "decision_out"}),
        (
            "observe_checkpoint",
            {"in_event_log": "in_event_log"},
            {"checkpoint_event": "checkpoint_event"},
        ),
        ("observe_wildcard", {"in_event": "in_event"}, {"wildcard_event": "wildcard_event"}),
    ],
    "act": [
        ("act_authorize", {"in_args": "in_args"}, {"allowed": "act_authorize_allowed"}),
        (
            "act_budget",
            {"in_args": "in_args", "in_state": "in_state"},
            {"allowed": "act_budget_allowed"},
        ),
        ("act_constrain", {"in_args": "in_args"}, {"allowed": "act_constrain_allowed"}),
        ("act_execute", {"in_args": "in_args"}, {"allowed": "act_execute_allowed"}),
        ("act_safe_boundary", {"in_args": "in_args"}, {"allowed": "act_safe_boundary_allowed"}),
        (
            "observe_checkpoint",
            {"in_event_log": "in_event_log"},
            {"checkpoint_event": "checkpoint_event"},
        ),
        ("observe_wildcard", {"in_event": "in_event"}, {"wildcard_event": "wildcard_event"}),
    ],
    "reflect": [
        (
            "observe_checkpoint",
            {"in_event_log": "in_event_log"},
            {"checkpoint_event": "checkpoint_event"},
        ),
        ("observe_wildcard", {"in_event": "in_event"}, {"wildcard_event": "wildcard_event"}),
    ],
    "memory": [
        ("remember_admit", {"in_observation": "in_observation"}, {"allowed": "remember_admit"}),
        (
            "observe_checkpoint",
            {"in_event_log": "in_event_log"},
            {"checkpoint_event": "checkpoint_event"},
        ),
        ("observe_wildcard", {"in_event": "in_event"}, {"wildcard_event": "wildcard_event"}),
    ],
    "stop": [
        (
            "stop_decide",
            {
                "in_decision": "in_decision",
                "in_observation": "in_observation",
                "in_reflection": "in_reflection",
                "in_state": "in_state",
            },
            {"stop_decision": "stop_decision", "terminal": "terminal"},
        ),
        # stop.focus is a PhaseContribution (not a ControlSlot enum member);
        # wired here alongside stop_decide because both belong to the stop
        # phase per the declarative-phase-graph bundle.
        (
            "stop_focus",
            {
                "in_state": "in_state",
                "in_decision": "in_decision",
            },
            {"focus_verdict": "focus_verdict"},
        ),
        (
            "observe_checkpoint",
            {"in_event_log": "in_event_log"},
            {"checkpoint_event": "checkpoint_event"},
        ),
        ("observe_wildcard", {"in_event": "in_event"}, {"wildcard_event": "wildcard_event"}),
    ],
}

@register_plugin
@dataclass(frozen=True)
class ControlSlotsPlugin(GraphPlugin):
    """Inserts control-slot sub_specs onto each phase host (idempotent)."""

    name: str = "default_control_slots"
    kind: str = "control_slots"
    binds: tuple = ()
    config: dict[str, Any] = field(default_factory=dict)

    def before_compile(self, spec: Any, sub_registry: dict[str, Any] | None = None) -> Any:
        # Plugin hook signature: (spec) per base class; extended to also
        # accept (spec, sub_registry) for compile-time registry augmentation.
        # Sub_registry is passed by the skeleton when present.
        if sub_registry is None:
            return spec

        # Load missing control/*.yaml into the caller's registry in place so
        # the runner can resolve inserted sub_spec ids at runtime.
        from pathlib import Path

        control_dir = Path(__file__).resolve().parents[1] / "graphs" / "configs" / "control"
        if control_dir.is_dir():
            try:
                from agent_lab.graphs.loader import load_spec
            except ImportError:  # pragma: no cover - hard dep
                load_spec = None  # type: ignore[assignment]
            if load_spec is not None:
                for path in sorted(control_dir.glob("*.yaml")):
                    try:
                        loaded = load_spec(path)
                    except Exception as exc:  # pragma: no cover - bad yaml
                        _log.warning("control slot spec %s load failed: %s", path, exc)
                        continue
                    if loaded.id not in sub_registry:
                        sub_registry[loaded.id] = loaded

        from agent_lab.graph.spec import InfoNode, SubSpecLink

        node_by_id: dict[str, InfoNode] = {n.id: n for n in spec.nodes}
        present_links: set[tuple[str, str]] = {
            (link.node_id, link.sub_spec_id) for link in spec.sub_specs
        }
        new_links: list[SubSpecLink] = []
        updated_node_ids: set[str] = set()

        for link in list(spec.sub_specs):
            target = sub_registry.get(link.sub_spec_id)
            if target is None:
                continue
            phase_name = getattr(target, "phase", None)
            if not phase_name:
                continue
            host = node_by_id.get(link.node_id)
            if host is None:
                continue
            wirings = _PHASE_OWNER_WIRING.get(phase_name, ())
            for sub_spec_id, input_map, output_map in wirings:
                if sub_spec_id not in sub_registry:
                    continue
                if (host.id, sub_spec_id) in present_links:
                    continue
                # Ensure the host node declares every input / output port
                # the slot needs. Extend if missing.
                new_ins = list(host.ins)
                new_outs = list(host.outs)
                changed = False
                for parent_port in input_map:
                    if parent_port not in new_ins:
                        new_ins.append(parent_port)
                        changed = True
                for parent_port in output_map.values():
                    if parent_port not in new_outs:
                        new_outs.append(parent_port)
                        changed = True
                if changed:
                    host = host.model_copy(update={"ins": new_ins, "outs": new_outs})
                    node_by_id[host.id] = host
                    updated_node_ids.add(host.id)
                new_links.append(
                    SubSpecLink(
                        node_id=host.id,
                        sub_spec_id=sub_spec_id,
                        input_map=input_map,
                        output_map=output_map,
                    )
                )
                present_links.add((host.id, sub_spec_id))

        if not new_links and not updated_node_ids:
            return spec
        new_nodes = [node_by_id[n.id] if n.id in updated_node_ids else n for n in spec.nodes]
        return spec.model_copy(
            update={
                "nodes": new_nodes,
                "sub_specs": [*spec.sub_specs, *new_links],
            }
        )


# Module-level sentinel — the compile skeleton fans before_compile to
# plugins whose spec lists ``kind: control_slots``. The plugin declares
# itself via the ``kind`` class attribute (see base.py register_plugin).

__all__ = ["ControlSlotsPlugin"]
