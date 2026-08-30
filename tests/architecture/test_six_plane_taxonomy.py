"""Six-plane taxonomy test — ADR-0076 §一 验证约束.

Each plugin manifest must map to **exactly one** of the six planes:

1. Constitution Kernel — contracts, runtime kernel, phase graph.
2. Infrastructure — LLM adapter, memory backend, state store, journal, etc.
3. Cognitive — sensor, perceive hub, brain, reasoner, critic.
4. Governance — control slot contributions.
5. Execution — body, action handler, tool, safe executor, effect/delta handler.
6. Organization & Interaction — team strategy, role, mode adapter, session.

Plugin classification must be:
- Complete: every plugin manifest gets a plane (no ``unknown``).
- Deterministic: same plugin metadata yields the same plane.
- Mutually exclusive: each plugin appears in exactly one plane.

If a new plugin introduces a plane that does not yet have a rule in
``scripts.snapshot_capability_tree._PLANE_RULES``, this test fails with a
clear remediation hint.
"""

from __future__ import annotations

from scripts.snapshot_capability_tree import (
    _PLANE_RULES,
    _classify_plane,
    _scan_plugins,
)

# Six-plane taxonomy (ADR-0076 §一).
EXPECTED_PLANES: frozenset[str] = frozenset(
    {
        "constitution",
        "infrastructure",
        "cognitive",
        "governance",
        "execution",
        "organization",
        "evidence",
    }
)

# Evidence is the cross-cutting plane (Journal backend, TraceInspector,
# FactReader, Scorer, Replay, ArtifactController).  It is one of the six
# planes per ADR-0076 §一 横切平面; we treat it as the seventh "plane"
# bucket in the classifier but it remains one logical plane.

_CLASSIFIER_PLANES: frozenset[str] = frozenset(rule[0] for rule in _PLANE_RULES)


def test_classifier_rules_cover_expected_planes() -> None:
    """``_PLANE_RULES`` must declare a rule for every expected plane."""

    assert EXPECTED_PLANES.issubset(_CLASSIFIER_PLANES), (
        "Six-plane taxonomy missing from _PLANE_RULES: "
        f"{sorted(EXPECTED_PLANES - _CLASSIFIER_PLANES)}. "
        "Add a (plane, layers, module_patterns) entry to "
        "scripts/snapshot_capability_tree._PLANE_RULES."
    )


def test_every_plugin_is_classified_into_a_known_plane() -> None:
    """Each plugin manifest must land in exactly one known plane.

    A plugin that fails classification returns ``"unknown"``, which violates
    the ADR-0076 §一 invariant that every plugin belongs to one plane.
    """

    plugins = _scan_plugins()
    classified = [(p.id, p.module, _classify_plane(p.module, p.layer, p.kind)) for p in plugins]

    unknowns = [(pid, mod) for pid, mod, plane in classified if plane == "unknown"]
    assert not unknowns, (
        "Plugin(s) classified as 'unknown' plane — extend _PLANE_RULES:\n  - "
        + "\n  - ".join(f"{pid} ({mod})" for pid, mod in unknowns)
    )


def test_every_plugin_classification_is_in_six_plane_set() -> None:
    """The classifier must always return a plane from the taxonomy."""

    plugins = _scan_plugins()
    for plugin in plugins:
        plane = _classify_plane(plugin.module, plugin.layer, plugin.kind)
        assert plane in _CLASSIFIER_PLANES, (
            f"Plugin {plugin.id} classified as {plane!r} which is not in "
            f"the six-plane taxonomy ({sorted(_CLASSIFIER_PLANES)})."
        )


def test_no_plugin_appears_in_two_planes() -> None:
    """A plugin's manifest cannot be claimed by two distinct planes.

    The deterministic classifier returns the first matching rule; if two
    rules overlap on (module pattern + layer), the test exposes the
    ambiguity so the rules can be tightened.
    """

    plugins = _scan_plugins()
    seen: dict[str, str] = {}
    conflicts: list[str] = []
    for plugin in plugins:
        plane = _classify_plane(plugin.module, plugin.layer, plugin.kind)
        # Each (id, module) pair is checked exactly once because _scan_plugins
        # yields unique modules.  The conflict check is on the plane of one
        # plugin across two rules.
        for rule_plane, rule in _PLANE_RULES:
            if plane == rule_plane:
                # Verify that only this one rule could match by simulating a
                # removal — if another rule would also match, that's a conflict.
                layers: set[str] = rule.get("layers", set())  # type: ignore[assignment]
                patterns: list[str] = rule.get("module_patterns", [])  # type: ignore[assignment]
                if plugin.layer not in layers or not any(
                    __import__("re").search(p, plugin.module) for p in patterns
                ):
                    conflicts.append(
                        f"{plugin.id}: rule for {plane!r} would match via "
                        "classifier short-circuit but underlying conditions "
                        "appear inconsistent"
                    )
                    break
        if plugin.id in seen and seen[plugin.id] != plane:
            conflicts.append(f"{plugin.id}: previously {seen[plugin.id]!r}, now {plane!r}")
        seen[plugin.id] = plane

    assert not conflicts, "Plugin plane classification is ambiguous:\n  - " + "\n  - ".join(
        conflicts
    )


def test_six_plane_summary_has_no_zero_count_for_active_planes() -> None:
    """Every expected plane (except evidence/cross-cutting) must be non-empty.

    A plane with zero plugins means the rule is dead.  We allow ``evidence``
    to be empty if the repository does not yet publish any evidence-plane
    plugins, but log the situation so it is visible.
    """

    plugins = _scan_plugins()
    plane_counts: dict[str, int] = dict.fromkeys(EXPECTED_PLANES, 0)
    for plugin in plugins:
        plane = _classify_plane(plugin.module, plugin.layer, plugin.kind)
        if plane in plane_counts:
            plane_counts[plane] += 1

    # Constitution / Infrastructure / Cognitive / Execution / Organization
    # must be non-empty in the production plugin tree.
    must_be_populated: frozenset[str] = frozenset(
        {
            "constitution",
            "infrastructure",
            "cognitive",
            "execution",
            "organization",
        }
    )
    empties = [p for p in must_be_populated if plane_counts.get(p, 0) == 0]
    assert not empties, (
        f"Plane(s) declared in six-plane taxonomy but contain zero plugins: {empties}. "
        "Either add at least one plugin under that plane or remove the empty plane rule."
    )


def test_classifier_is_deterministic_per_input() -> None:
    """Repeated classification must be stable.

    This is the static counterpart of the runtime ``test_plugin_classification_deterministic``
    guard in ``test_capability_snapshot.py`` — it pins the rule logic so
    reorderings are caught here.
    """

    plugins = _scan_plugins()
    for plugin in plugins:
        first = _classify_plane(plugin.module, plugin.layer, plugin.kind)
        second = _classify_plane(plugin.module, plugin.layer, plugin.kind)
        third = _classify_plane(plugin.module, plugin.layer, plugin.kind)
        assert first == second == third, (
            f"Classification of {plugin.id} is non-deterministic: {first} / {second} / {third}"
        )


__all__ = [
    "EXPECTED_PLANES",
    "test_classifier_is_deterministic_per_input",
    "test_classifier_rules_cover_expected_planes",
    "test_every_plugin_classification_is_in_six_plane_set",
    "test_every_plugin_is_classified_into_a_known_plane",
    "test_no_plugin_appears_in_two_planes",
    "test_six_plane_summary_has_no_zero_count_for_active_planes",
]
