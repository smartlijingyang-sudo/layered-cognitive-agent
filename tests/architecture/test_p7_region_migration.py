"""ADR-0210 §6.2 — P7 region migration tests.

Verifies:
  - The 6 phase worker carriers (perceive / think / act / reflect /
    remember) all use the recommended region set.
  - The bare enum regions (model_visible / effect / lineage / digest
    / control) are accepted.
  - profile.regions.declare extends the closed set.
  - region labels do NOT participate in the capability closed set
    (capability-closed-set.md §1.4 has no `region:*` entries).
  - Unbound region labels fail compilation.
  - Backward compat: 0075 / 0194 paths still work (phase_graph
    Optional).
"""

import subprocess
from pathlib import Path

import pytest
import yaml

from agent_lab.graph.spec import (
    InfoEdgeSpec,
    InfoGrant,
    InfoNode,
    NodeRegion,
    PluginRef,
)
from agent_lab.graph.validate import (
    ValidationError,
    _check_regions,
    validate_with_profile,
    validate_with_profile_or_raise,
)
from agent_lab.profile_loader import (
    BUILTIN_BARE_REGIONS,
    BUILTIN_PHASE_REGIONS,
    build_region_closed_set,
    load_profile_regions,
    region_label_for_node,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _spec(region: NodeRegion, phase: str = "", nodes=()) -> InfoEdgeSpec:
    """Build a spec with the given spec-level region + phase."""
    return InfoEdgeSpec(
        id="test",
        version="0.1.0",
        region=region,
        description="",
        phase=phase,
        nodes=list(nodes),
        edges=[],
        grants=[],
        sub_specs=[],
        plugins=[],
        discard_sink=None,
    )


# ---------------------------------------------------------------------------
# 6-stage recommended region
# ---------------------------------------------------------------------------

class TestSixPhaseRecommendedRegions:
    """Every phase worker carrier must use a region in the 6-stage set."""

    def test_six_stage_set_is_complete(self):
        assert set(BUILTIN_PHASE_REGIONS) == {
            "phase:perceive",
            "phase:think",
            "phase:act",
            "phase:reflect",
            "phase:remember",
            "phase:stop",
        }

    def test_bare_enum_set_is_separate(self):
        """Bare enum regions are not phase regions; they have no `phase:` prefix."""
        assert set(BUILTIN_BARE_REGIONS) == {
            "model_visible",
            "effect",
            "lineage",
            "digest",
            "control",
        }

    def test_validate_accepts_all_six_phase_specs(self):
        # One spec per stage — each has its own region label
        # (region=PHASE, phase=<stage>).
        c14 = []
        for stage in ("perceive", "think", "act", "reflect", "remember", "stop"):
            spec = _spec(NodeRegion.PHASE, phase=stage)
            errs = validate_with_profile(spec, profile_regions=None)
            c14 += [e for e in errs if e.startswith("C14:")]
        assert c14 == [], f"unexpected C14 errors: {c14}"

    def test_validate_accepts_bare_enum_specs(self):
        c14 = []
        for region in (
            NodeRegion.MODEL_VISIBLE,
            NodeRegion.EFFECT,
            NodeRegion.LINEAGE,
            NodeRegion.DIGEST,
            NodeRegion.CONTROL,
        ):
            spec = _spec(region)
            errs = validate_with_profile(spec)
            c14 += [e for e in errs if e.startswith("C14:")]
        assert c14 == []


# ---------------------------------------------------------------------------
# profile.regions.declare extension
# ---------------------------------------------------------------------------

class TestProfileRegionExtension:
    """profile.regions.declare extends the closed set; unknown regions fail."""

    def test_unknown_region_fails(self):
        # Spec with custom phase name not in 6-stage set, no profile
        spec = _spec(NodeRegion.PHASE, phase="totally_made_up")
        errs = validate_with_profile(spec, profile_regions=set())
        c14 = [e for e in errs if e.startswith("C14:")]
        assert len(c14) == 1
        assert "phase:totally_made_up" in c14[0]
        assert "test" in c14[0]  # spec id is "test"

    def test_profile_extends_region(self):
        # Spec with phase "plan" — not in 6-stage set
        spec = _spec(NodeRegion.PHASE, phase="plan")
        # No profile: should fail (phase:plan not in 6-stage set)
        errs_no_profile = validate_with_profile(spec, profile_regions=set())
        assert any("phase:plan" in e for e in errs_no_profile)

        # With profile declaring the region: should pass
        errs_with_profile = validate_with_profile(
            spec, profile_regions={"phase:plan"}
        )
        c14 = [e for e in errs_with_profile if e.startswith("C14:")]
        assert c14 == [], f"unexpected errors: {c14}"


# ---------------------------------------------------------------------------
# region NOT in capability closed set (P7-I-2)
# ---------------------------------------------------------------------------

class TestRegionNotInCapabilityClosedSet:
    """region labels must not appear in docs/specs/capability-closed-set.md."""

    def test_no_region_in_capability_spec(self):
        spec_path = Path("docs/specs/capability-closed-set.md")
        if not spec_path.exists():
            pytest.skip("capability-closed-set.md not found")
        text = spec_path.read_text(encoding="utf-8")
        # Extract the closed set list (between ```text ``` fences).
        import re
        m = re.search(r"```text\n(.*?)```", text, re.DOTALL)
        assert m, "no fenced closed set in spec"
        closed = m.group(1)
        # Any "region:..." key in the closed set would violate P7-I-2.
        # (A region label should not be a capability key.)
        region_keys = re.findall(r'"(region[:.][^"]+)"', closed)
        assert region_keys == [], (
            f"region labels leaked into capability closed set: {region_keys}"
        )

    def test_region_label_helper(self):
        """region_label_for_node expands the bare phase into phase:<name>."""
        assert region_label_for_node("phase", "think") == "phase:think"
        assert region_label_for_node("phase", "act") == "phase:act"
        # Bare enums pass through.
        assert region_label_for_node("control", "") == "control"
        # Unknown enum stays as-is (closed-set check will reject it).
        assert region_label_for_node("model_visible", "") == "model_visible"


# ---------------------------------------------------------------------------
# Backward compat: 0075 / 0194 CognitivePhaseGraphPlan still works
# ---------------------------------------------------------------------------

class TestBackwardCompat0075_0194:
    """The old 0075 / 0194 path (phase_graph: Optional) still validates."""

    def test_phase_graph_optional_unchanged(self):
        """CompiledRunPlan.phase_graph is still Optional; None is valid.

        Verified via type-hint inspection (avoiding CompiledRunPlan
        constructor internals which are not the contract under test).
        """
        from lca.contracts.protocols.state.plan import CompiledRunPlan
        from typing import get_type_hints
        hints = get_type_hints(CompiledRunPlan)
        ph_graph_type = str(hints.get("phase_graph", ""))
        assert "Optional" in ph_graph_type or "None" in ph_graph_type, (
            f"phase_graph must be Optional per ADR-0210 §2.1, "
            f"got annotation: {ph_graph_type!r}"
        )
        # Default value is None
        assert CompiledRunPlan.__dataclass_fields__["phase_graph"].default is None

    def test_0075_capability_closure_unchanged(self):
        """The `phase.<name>.<executor>` capability closure is unaffected by P7.

        Per ADR-0210 §2.2 — region labels do NOT enter the capability
        closed set. PhaseExecutor selection still goes through the
        closure as before.
        """
        # Static check: ensure the closed set has no `region:` entries
        # (only the `phase.<name>.<executor>` capability shape).
        result = subprocess.run(
            ["grep", "-E", "lab\\.region|region[:.]", "docs/specs/capability-closed-set.md"],
            capture_output=True, text=True
        )
        assert result.stdout.strip() == "", (
            f"region leaked into capability spec: {result.stdout}"
        )


# ---------------------------------------------------------------------------
# Profile loader (real YAML reading)
# ---------------------------------------------------------------------------

class TestProfileLoader:
    """load_profile_regions() reads regions.declare from a profile YAML."""

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_profile_regions(tmp_path / "nope.yaml") == set()

    def test_no_regions_section_returns_empty(self, tmp_path):
        p = tmp_path / "profile.yaml"
        p.write_text("bundles:\n  - bundles/base.yaml\n")
        assert load_profile_regions(p) == set()

    def test_reads_declare_list(self, tmp_path):
        p = tmp_path / "profile.yaml"
        p.write_text(yaml.safe_dump({
            "regions": {
                "declare": ["phase:plan", "phase:replan", "control:safety"]
            }
        }))
        assert load_profile_regions(p) == {"phase:plan", "phase:replan", "control:safety"}

    def test_non_list_declare_returns_empty(self, tmp_path):
        p = tmp_path / "profile.yaml"
        p.write_text(yaml.safe_dump({"regions": {"declare": "not-a-list"}}))
        assert load_profile_regions(p) == set()

    def test_build_region_closed_set_combines(self):
        closed = build_region_closed_set({"phase:plan"})
        # Builtins + custom
        assert "phase:perceive" in closed
        assert "phase:plan" in closed
        assert "control" in closed
        # Nothing custom leaked
        assert "phase:made_up" not in closed


# ---------------------------------------------------------------------------
# or_raise integration
# ---------------------------------------------------------------------------

class TestValidateOrRaiseWithProfile:
    def test_raises_on_unknown_region(self):
        spec = _spec(NodeRegion.PHASE, phase="nope")
        with pytest.raises(ValidationError) as exc_info:
            validate_with_profile_or_raise(spec, profile_regions=set())
        assert any("phase:nope" in str(e) for e in exc_info.value.errors)

    def test_does_not_raise_on_valid(self):
        spec = _spec(NodeRegion.PHASE, phase="perceive")
        # Should not raise.
        validate_with_profile_or_raise(spec, profile_regions=set())