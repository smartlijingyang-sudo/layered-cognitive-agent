"""Pin the graph phase-alias vocabulary against real bundle YAMLs (RA-109).

``phase_of`` / ``LCA_TOP_PHASES`` / ``_PHASE_ALIAS_OF`` were hand-maintained
with zero test references: any bundle node whose first segment was neither
a top phase nor an alias silently rendered ``phase=""`` in NodeEnter/NodeExit
facts. This test walks every node id declared in ``bundles/**/*.yaml`` and
asserts each non-empty node id maps to a recognised top phase or alias — or
to a documented keep-list prefix that legitimately has no lifecycle phase.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from lca.framework.graph.observation import (
    _PHASE_ALIAS_OF,
    LCA_TOP_PHASES,
    phase_of,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLES_DIR = REPO_ROOT / "bundles"

# Prefixes that legitimately have no lifecycle phase; ``phase_of`` returns
# "" for them by design and forcing an alias would fabricate a phase.
#
# Evidence:
# - plan / intervene / delegate: ADR-0228 — "not added to the six-phase
#   closed set. They are cross-phase subgraphs invoked from the outer
#   phase_main.yaml topology" (region directories beside the six phases).
# - primitive: Layer 1 phase-agnostic primitives (bundles/primitive/*) not
#   wired into any phase subgraph via ``sub_spec_ref``.
_LEGITIMATE_NO_PHASE_PREFIXES: frozenset[str] = frozenset(
    {"delegate", "intervene", "plan", "primitive"}
)


def _node_ids_in_yaml(data: object) -> set[str]:
    """Collect every node id declared in one parsed bundle graph spec.

    Node ids live under ``nodes:`` lists (each entry carries ``id``). Nested
    subgraph specs are separate bundle files, so a plain recursive walk of
    the parsed document is sufficient.
    """
    ids: set[str] = set()
    stack: list[object] = [data]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            nodes = current.get("nodes")
            if isinstance(nodes, list):
                for node in nodes:
                    if isinstance(node, dict) and isinstance(node.get("id"), str):
                        ids.add(node["id"])
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return ids


def _bundle_node_ids() -> set[str]:
    """Walk every ``nodes:`` id across the real bundle corpus."""
    ids: set[str] = set()
    for path in sorted(BUNDLES_DIR.rglob("*.yaml")):
        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        ids.update(_node_ids_in_yaml(data))
    return ids


def test_every_bundle_node_id_maps_to_phase_or_keep_list() -> None:
    """No real bundle node silently renders ``phase=""`` (RA-109 AC1)."""
    node_ids = _bundle_node_ids()
    assert node_ids, "bundles corpus must contain at least one node id"
    unmapped = sorted(
        node_id
        for node_id in node_ids
        if not phase_of(node_id) and node_id.split(".", 1)[0] not in _LEGITIMATE_NO_PHASE_PREFIXES
    )
    assert not unmapped, (
        "bundle node ids silently render phase='': "
        + ", ".join(unmapped)
        + ". Extend _PHASE_ALIAS_OF with evidence or add the head to "
        "_LEGITIMATE_NO_PHASE_PREFIXES."
    )


def test_alias_table_maps_every_alias_to_a_top_phase() -> None:
    """Each alias resolves to a canonical top phase (RA-109 AC2)."""
    assert _PHASE_ALIAS_OF, "alias table must not be empty"
    for alias, phase in _PHASE_ALIAS_OF.items():
        assert phase in LCA_TOP_PHASES, f"alias {alias!r} -> non-phase {phase!r}"
        assert phase_of(f"{alias}.any.node") == phase


def test_top_phases_map_to_themselves() -> None:
    """Canonical ``<phase>.<subnode>`` naming keeps its own phase."""
    for phase in LCA_TOP_PHASES:
        assert phase_of(f"{phase}.subnode") == phase


def test_keep_list_prefixes_legitimately_have_no_phase() -> None:
    """Keep-listed heads are documented no-phase prefixes, not aliases."""
    for head in _LEGITIMATE_NO_PHASE_PREFIXES:
        assert phase_of(f"{head}.any.node") == ""


def test_phase_of_empty_and_unknown_returns_empty() -> None:
    """Empty node id and unrecognised prefixes yield the unknown marker."""
    assert phase_of("") == ""
    assert phase_of("not-a-real-phase.node") == ""


def test_real_bundle_nodes_map_with_evidence() -> None:
    """Concrete think-turn nodes dropped their ``think.`` prefix (AC2)."""
    assert phase_of("reason.prepare.role") == "think"
    assert phase_of("context.lines.collect") == "think"
    assert phase_of("prompt.candidate.enumerate") == "think"
    assert phase_of("shortcut.try") == "think"
    assert phase_of("capability.role.normalize") == "think"
    # Cross-phase regions stay phase-less by design (ADR-0228).
    assert phase_of("plan.compose") == ""
    assert phase_of("intervene.interrupt") == ""
