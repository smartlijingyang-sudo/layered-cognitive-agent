"""Profile region declarations (ADR-0210 §1.4 + §6.2).

A profile YAML may declare custom region tags beyond the 6-stage
recommended set:

  regions:
    declare:
      - phase:plan
      - phase:replan
      - control:safety

These custom regions are read by `agent_lab.graph.validate` (C14)
when the profile is supplied to `validate(spec, profile_regions=...)`.
The compiler checks every InfoNode.region against the union of:

  - The 6-stage recommended set: phase:perceive / phase:think /
    phase:act / phase:reflect / phase:remember / phase:stop
  - profile.regions.declare (custom set)
  - bare enum values: model_visible / effect / lineage / digest / control

delete-when: ADR-0210 升 Accepted. (The mechanism is part of P7.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# The 6-stage recommended region tag set. These are checked FIRST in
# the C14 region validation; the profile.regions.declare list is added
# on top of this set.
BUILTIN_PHASE_REGIONS: tuple[str, ...] = (
    "phase:perceive",
    "phase:think",
    "phase:act",
    "phase:reflect",
    "phase:remember",
    "phase:stop",
)

# Bare enum values (matching agent_lab.graph.spec.NodeRegion members).
# These do NOT carry the ``phase:`` prefix.
BUILTIN_BARE_REGIONS: tuple[str, ...] = (
    "model_visible",
    "effect",
    "lineage",
    "digest",
    "control",
)


def _normalize_region_label(value: str) -> str:
    """Map an InfoNode.region value to a profile region label.

    agent_lab.graph.spec stores the region as a NodeRegion enum value
    (e.g. "phase") with the actual phase name in the separate `phase`
    field. This function reconstructs the "region: phase:<name>" label
    that C14 uses for validation.
    """
    if value.startswith("phase:"):
        return value  # already a full label
    # Otherwise, treat as a bare enum value (no expansion).
    return value


def load_profile_regions(profile_path: str | Path) -> set[str]:
    """Parse the ``regions.declare:`` section of a profile YAML.

    Returns a set of region labels (e.g. ``{"phase:plan", "phase:replan"}``).
    Missing file or missing section returns an empty set.
    """
    import yaml

    p = Path(profile_path)
    if not p.exists():
        return set()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return set()
    if not isinstance(data, dict):
        return set()
    regions = data.get("regions") or {}
    if not isinstance(regions, dict):
        return set()
    declared = regions.get("declare") or []
    if not isinstance(declared, list):
        return set()
    out: set[str] = set()
    for item in declared:
        if isinstance(item, str) and item:
            out.add(item)
    return out


def build_region_closed_set(profile_regions: set[str] | None) -> set[str]:
    """Return the full set of region labels accepted by C14.

    Combines:
      - The 6-stage recommended phase regions
      - The bare enum regions (model_visible / effect / etc.)
      - Any profile.regions.declare custom set

    Returns the same set whether profile_regions is None (just the
    builtins) or a custom set.
    """
    closed: set[str] = set(BUILTIN_PHASE_REGIONS) | set(BUILTIN_BARE_REGIONS)
    if profile_regions:
        closed |= set(profile_regions)
    return closed


def region_label_for_node(region_enum: str, phase_name: str) -> str:
    """Compute the full region label for an InfoNode from its enum + phase.

    ``region_enum`` is a NodeRegion.value (e.g. "phase"); ``phase_name`` is
    the bare phase name (e.g. "think"). Returns the full label
    "phase:think" used by the C14 closed set check.
    """
    if region_enum == "phase" and phase_name:
        return f"phase:{phase_name}"
    return region_enum


__all__ = [
    "BUILTIN_PHASE_REGIONS",
    "BUILTIN_BARE_REGIONS",
    "build_region_closed_set",
    "load_profile_regions",
    "region_label_for_node",
    "_normalize_region_label",
]

# ---------------------------------------------------------------------------
# ADR-0210 §6.4 — region-tag phase graph synthesis
# ---------------------------------------------------------------------------

def build_region_only_phase_graph(
    spec,
    region_label: str | None = None,
) -> "CognitivePhaseGraphPlan":
    """Build a minimal CognitivePhaseGraphPlan from a spec's region.

    Per ADR-0210 §2.1 + §6.4: when a CompiledRunPlan.phase_graph is None
    (the P7 path), the GenericPlanInterpreter must still be able to
    drive execution. We synthesize a single-node CognitivePhaseGraphPlan
    whose entry + terminal == spec.id, with semantic_phase derived from
    the region label (if it matches a SemanticPhase) or 'act' as
    a safe default.

    This keeps the interpreter's "one phase per run" semantics intact
    while honouring ADR-0210 §2.1 ("phase_graph: None is legal").
    """
    from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
        CognitivePhaseGraphPlan,
        PhaseEdge,
        PhaseNode,
    )
    from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
        SemanticPhase,
    )

    if region_label is None:
        region_label = region_label_for_node(
            spec.region.value if hasattr(spec.region, "value") else str(spec.region),
            getattr(spec, "phase", "") or "",
        )

    # Map region label to SemanticPhase (only the 6 stages map cleanly).
    phase_name = region_label.split(":", 1)[1] if region_label.startswith("phase:") else ""
    if phase_name in {p.value for p in SemanticPhase}:
        semantic_phase = SemanticPhase(phase_name)
    else:
        # Bare-enum region (model_visible / effect / etc.) or custom
        # region (phase:plan / etc.) — fall back to 'act' so the
        # interpreter can drive; downstream PhaseBinding.executor_capability
        # closure selects the real executor.
        semantic_phase = SemanticPhase.ACT

    # Single-node plan: entry + terminal == spec.id
    # entry is set on the plan (CognitivePhaseGraphPlan.entry), not on
    # the PhaseNode. terminal=True is the single PhaseNode property.
    node = PhaseNode(
        id=spec.id,
        semantic_phase=semantic_phase,
        binding=f"phase.{semantic_phase.value}.subgraph",
        max_visits=1,
        terminal=True,
    )
    return CognitivePhaseGraphPlan(
        entry=spec.id,
        nodes=(node,),
        edges=(),
        approval_resume_node=None,
    )


__all__ += ["build_region_only_phase_graph"]
