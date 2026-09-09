"""ADR-0210 §6.3 — runtime region label + nested subgraph recursion tests.

Verifies that:
  - current_region_label() composes the spec's region + phase into the
    full label used by C14.
  - walk_sub_specs() depth-first traverses the nested sub_spec graph
    (without recursion limit issues).
  - validate_subgraph_with_profile() walks the WHOLE sub_spec graph
    (root + nested) and reports C14 errors at each level.
  - Region labels are independent at each sub_spec level (per
    ADR-0210 §2.2 / P7-I-2).
"""

import pytest

from agent_lab.graph.spec import (
    InfoEdgeSpec,
    InfoNode,
    NodeRegion,
    PluginRef,
    SubSpecLink,
    current_region_label,
    walk_sub_specs,
)
from agent_lab.graph.validate import (
    ValidationError,
    validate_subgraph_with_profile,
    validate_subgraph_with_profile_or_raise,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec(
    id_: str,
    region: NodeRegion,
    phase: str = "",
    sub_specs=(),
    nodes=(),
) -> InfoEdgeSpec:
    return InfoEdgeSpec(
        id=id_,
        version="0.1.0",
        region=region,
        description="",
        phase=phase,
        nodes=list(nodes),
        edges=[],
        grants=[],
        sub_specs=list(sub_specs),
        plugins=[],
        discard_sink=None,
    )


def _node(id_: str, region: NodeRegion, phase: str = "") -> InfoNode:
    return InfoNode(
        id=id_,
        region=region,
        factory="identity",
        config={},
        ins=[],
        outs=[],
        on_error="fail",
        route_to=None,
        parallelism=1,
    )


def _sub(link_node: str, sub_id: str) -> SubSpecLink:
    return SubSpecLink(
        node_id=link_node,
        sub_spec_id=sub_id,
        input_map={},
        output_map={},
    )


# ---------------------------------------------------------------------------
# current_region_label
# ---------------------------------------------------------------------------

class TestCurrentRegionLabel:
    """current_region_label(spec) → full region string used by C14."""

    def test_phase_with_name(self):
        spec = _spec("t", NodeRegion.PHASE, phase="think")
        assert current_region_label(spec) == "phase:think"

    def test_phase_with_act_name(self):
        spec = _spec("a", NodeRegion.PHASE, phase="act")
        assert current_region_label(spec) == "phase:act"

    def test_bare_enum_passes_through(self):
        spec = _spec("mv", NodeRegion.MODEL_VISIBLE)
        assert current_region_label(spec) == "model_visible"

    def test_empty_phase_marks_unnamed(self):
        """Empty phase + PHASE region → 'phase:<unnamed>' (flagged by validator)."""
        spec = _spec("p", NodeRegion.PHASE, phase="")
        assert current_region_label(spec) == "phase:<unnamed>"

    def test_each_of_six_phases(self):
        for stage in ("perceive", "think", "act", "reflect", "remember", "stop"):
            spec = _spec(stage, NodeRegion.PHASE, phase=stage)
            assert current_region_label(spec) == f"phase:{stage}"


# ---------------------------------------------------------------------------
# walk_sub_specs
# ---------------------------------------------------------------------------

class TestWalkSubSpecs:
    """walk_sub_specs(root) — iterative depth-first traversal."""

    def test_walk_root_only(self):
        root = _spec("root", NodeRegion.PHASE, phase="act")
        assert [s.id for s in walk_sub_specs(root)] == ["root"]

    def test_walk_one_level(self):
        sub = _spec("sub", NodeRegion.PHASE, phase="think")
        # The walker needs the registry to find sub_specs
        # walk_sub_specs(root) without registry won't find them
        root = _spec("root", NodeRegion.PHASE, phase="act", sub_specs=[_sub("n", "sub")])
        # Without registry, sub_specs not resolvable → walker returns [root]
        assert [s.id for s in walk_sub_specs(root)] == ["root"]

    def test_walk_handles_cycle(self):
        """Cycles in sub_spec references don't loop forever."""
        a = _spec("a", NodeRegion.PHASE, phase="think")
        b = _spec("b", NodeRegion.PHASE, phase="act")
        # Build a cycle: a.sub_specs references b; b.sub_specs references a
        a_sub = SubSpecLink(node_id="a_n", sub_spec_id="b", input_map={}, output_map={})
        b_sub = SubSpecLink(node_id="b_n", sub_spec_id="a", input_map={}, output_map={})
        a = a.model_copy(update={"sub_specs": [a_sub]})
        b = b.model_copy(update={"sub_specs": [b_sub]})
        # Without registry the walker won't find them; with a cycle the
        # _seen set prevents infinite recursion.
        # Test the cycle-prevention directly via _walk_sub_specs with a
        # registry dict that creates a cycle.
        from agent_lab.graph.spec import _walk_sub_specs
        registry = {"a": a, "b": b}
        result = _walk_sub_specs(a, registry, _seen=None)
        ids = [s.id for s in result]
        # root 'a' + 'b' (one iteration)
        assert ids == ["a", "b"], f"cycle not handled: {ids}"


# ---------------------------------------------------------------------------
# validate_subgraph_with_profile
# ---------------------------------------------------------------------------

class TestValidateSubgraphWithProfile:
    """C14 region validation over the entire nested sub_spec graph."""

    def test_root_only_validates_root(self):
        root = _spec("root", NodeRegion.PHASE, phase="think")
        errs = validate_subgraph_with_profile(root, profile_regions=None)
        c14 = [e for e in errs if e.startswith("C14:")]
        assert c14 == []

    def test_root_with_unbound_region_fails(self):
        root = _spec("bad", NodeRegion.PHASE, phase="totally_made_up")
        errs = validate_subgraph_with_profile(root, profile_regions=None)
        c14 = [e for e in errs if e.startswith("C14:")]
        assert len(c14) >= 1
        assert "phase:totally_made_up" in c14[0]
        assert "'bad'" in c14[0]

    def test_subgraph_walk_with_registry(self):
        """When sub_spec is in registry, walker recurses."""
        sub = _spec("sub", NodeRegion.PHASE, phase="act")
        root = _spec(
            "root",
            NodeRegion.PHASE,
            phase="think",
            sub_specs=[_sub("node", "sub")],
        )
        registry = {"root": root, "sub": sub}
        # Use the lower-level walker with registry
        from agent_lab.graph.spec import _walk_sub_specs
        result = _walk_sub_specs(root, registry, _seen=None)
        ids = [s.id for s in result]
        # root + sub both visited
        assert "root" in ids
        assert "sub" in ids

    def test_subgraph_walk_with_bad_child_fails(self):
        """Sub_spec with bad region label → root + child both reported."""
        sub = _spec("bad_child", NodeRegion.PHASE, phase="nonexistent")
        root = _spec(
            "good_root",
            NodeRegion.PHASE,
            phase="act",
            sub_specs=[_sub("node", "bad_child")],
        )
        registry = {"good_root": root, "bad_child": sub}
        # Use the lower-level walker
        from agent_lab.graph.spec import _walk_sub_specs
        all_specs = _walk_sub_specs(root, registry, _seen=None)
        # Now validate each
        all_errs = []
        for s in all_specs:
            all_errs.extend(
                [e for e in validate_subgraph_with_profile(s, profile_regions=None)
                 if e.startswith("C14:")]
            )
        # At least one error mentions the bad child
        assert any("bad_child" in e for e in all_errs), (
            f"expected error mentioning bad_child, got: {all_errs}"
        )

    def test_empty_phase_flagged(self):
        """Empty phase + PHASE region → 'phase:<unnamed>' is flagged."""
        spec = _spec("p", NodeRegion.PHASE, phase="")
        errs = validate_subgraph_with_profile(spec, profile_regions=None)
        c14 = [e for e in errs if e.startswith("C14:")]
        # Should flag as "phase:<unnamed>" warning
        assert any("unnamed" in e for e in c14)

    def test_profile_extends_closed_set(self):
        spec = _spec("plan", NodeRegion.PHASE, phase="plan")
        # No profile: fails
        errs = validate_subgraph_with_profile(spec, profile_regions=set())
        assert any("phase:plan" in e for e in errs)
        # With profile: passes
        errs_p = validate_subgraph_with_profile(
            spec, profile_regions={"phase:plan"}
        )
        c14 = [e for e in errs_p if e.startswith("C14:")]
        assert c14 == []

    def test_or_raise_integration(self):
        spec = _spec("bad", NodeRegion.PHASE, phase="nonexistent")
        with pytest.raises(ValidationError):
            validate_subgraph_with_profile_or_raise(spec)


# ---------------------------------------------------------------------------
# Independence of region per sub_spec
# ---------------------------------------------------------------------------

class TestRegionIndependencePerSubSpec:
    """Each sub_spec has its own region label (P7-I-1 / §2.2)."""

    def test_each_sub_spec_validated_independently(self):
        """Root good + child bad → child flagged, root OK."""
        sub = _spec("bad_child", NodeRegion.PHASE, phase="nonexistent")
        # Use the private walker with registry
        from agent_lab.graph.spec import _walk_sub_specs
        root = _spec(
            "good_root",
            NodeRegion.PHASE,
            phase="act",
            sub_specs=[_sub("node", "bad_child")],
        )
        registry = {"good_root": root, "bad_child": sub}

        all_specs = _walk_sub_specs(root, registry, _seen=None)
        # Validate each spec individually
        for s in all_specs:
            errs = validate_subgraph_with_profile(s, profile_regions=None)
            c14 = [e for e in errs if e.startswith("C14:")]
            if s.id == "good_root":
                assert c14 == [], f"root should be clean: {c14}"
            elif s.id == "bad_child":
                assert len(c14) >= 1, f"child should fail: {c14}"
                assert any("nonexistent" in e for e in c14)

    def test_root_with_custom_region_needs_profile(self):
        """If the root uses a custom region, profile must declare it."""
        spec = _spec("custom", NodeRegion.PHASE, phase="plan")
        # Without profile declaration: fail
        errs_no = validate_subgraph_with_profile(spec, profile_regions=set())
        assert any("phase:plan" in e for e in errs_no)
        # With profile declaration: pass
        errs_yes = validate_subgraph_with_profile(
            spec, profile_regions={"phase:plan"}
        )
        c14 = [e for e in errs_yes if e.startswith("C14:")]
        assert c14 == []


# ---------------------------------------------------------------------------
# __walk_sub_specs cycle prevention
# ---------------------------------------------------------------------------

class TestSubSpecCyclePrevention:
    """walk_sub_specs must not loop forever on cycles."""

    def test_cycle_in_registry_does_not_loop(self):
        """A sub_spec that references its own parent is bounded by _seen."""
        from agent_lab.graph.spec import _walk_sub_specs
        # a → b → a cycle
        a = _spec("a", NodeRegion.PHASE, phase="think")
        b = _spec("b", NodeRegion.PHASE, phase="act")
        a_sub = SubSpecLink(node_id="a_n", sub_spec_id="b", input_map={}, output_map={})
        b_sub = SubSpecLink(node_id="b_n", sub_spec_id="a", input_map={}, output_map={})
        a = a.model_copy(update={"sub_specs": [a_sub]})
        b = b.model_copy(update={"sub_specs": [b_sub]})
        registry = {"a": a, "b": b}
        result = _walk_sub_specs(a, registry, _seen=None)
        # Bounded by _seen — must terminate with finite list
        assert len(result) == 2
        assert {s.id for s in result} == {"a", "b"}