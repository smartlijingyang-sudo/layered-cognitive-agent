"""ADR-0210 §6.6 — real production profile verification tests.

Verifies that ``profiles/web-assistant.yaml`` declares the P7
region-tag closed set extension via ``regions.declare``:

  - phase:plan
  - phase:replan
  - control:safety

The closed set extension lets the GenericPlanInterpreter fallback
(per ADR-0210 §6.4) accept custom regions in production paths.
The C14 closed-set check (per ADR-0210 §3 P7-I-4) reads these from
the profile and accepts them as legal region labels.
"""

import pathlib

import pytest
import yaml


REGIONS_DECLARED = ("phase:plan", "phase:replan", "control:safety")


class TestWebAssistantRegionsDeclared:
    """The web-assistant profile must declare the 3 P7 custom regions."""

    def test_yaml_is_valid(self):
        f = pathlib.Path("profiles/web-assistant.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"profile parse failed: {data!r}"
        assert "regions" in data, (
            "web-assistant.yaml must declare 'regions:' (ADR-0210 §6.6)"
        )

    def test_regions_declare_section_exists(self):
        f = pathlib.Path("profiles/web-assistant.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        regions = data["regions"]
        assert "declare" in regions, (
            "regions section must contain 'declare:' (ADR-0210 §6.2 schema)"
        )

    def test_three_custom_regions_declared(self):
        f = pathlib.Path("profiles/web-assistant.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        declared = data["regions"]["declare"]
        assert tuple(declared) == REGIONS_DECLARED, (
            f"web-assistant must declare exactly {REGIONS_DECLARED}, got {declared}"
        )

    def test_phase_plan_first(self):
        f = pathlib.Path("profiles/web-assistant.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        declared = data["regions"]["declare"]
        assert declared[0] == "phase:plan", (
            f"first declared region must be phase:plan, got {declared[0]}"
        )

    def test_control_safety_in_declare(self):
        f = pathlib.Path("profiles/web-assistant.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        declared = data["regions"]["declare"]
        assert "control:safety" in declared, (
            "control:safety (custom control region) must be in declare list"
        )


class TestParseRegionsDeclareIsolated:
    """The internal _parse_regions_declare parser behaves correctly.

    Tested in isolation (without triggering the cordis-bound module
    imports in lca.harness.profile.resolve.source). The function is
    extracted to source.py by reading the file's AST and compiling
    the function in isolation.
    """

    def _extract_and_call(self, raw):
        """Compile _parse_regions_declare from source.py and call it.

        We use AST extraction + exec to avoid the cordis import chain
        triggered by ``from lca.harness.profile.resolve.source import ...``
        (the source module imports cordis at module top via
        lca.harness.profile.boot).
        """
        import ast
        import typing
        from pathlib import Path as _P
        text = _P("lca/harness/profile/resolve/source.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        # Find the function definition
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_parse_regions_declare":
                module = ast.Module(body=[node], type_ignores=[])
                ns: dict = {"Any": typing.Any, "Mapping": typing.Mapping}
                exec(compile(module, "<ast>", "exec"), ns)
                return ns["_parse_regions_declare"](raw)
        raise RuntimeError("_parse_regions_declare not found in source.py")

    def test_valid_declare(self):
        result = self._extract_and_call({
            "regions": {"declare": ["phase:plan", "phase:replan"]}
        })
        assert result == ("phase:plan", "phase:replan")

    def test_missing_regions_section_returns_empty(self):
        result = self._extract_and_call({})
        assert result == ()

    def test_regions_not_a_dict_returns_empty(self):
        result = self._extract_and_call({"regions": "not-a-dict"})
        assert result == ()

    def test_missing_declare_returns_empty(self):
        result = self._extract_and_call({"regions": {}})
        assert result == ()

    def test_declare_not_a_list_returns_empty(self):
        result = self._extract_and_call({"regions": {"declare": "not-a-list"}})
        assert result == ()

    def test_filters_non_string_entries(self):
        """Non-string entries (None, dict, int) are silently filtered out."""
        result = self._extract_and_call({
            "regions": {"declare": ["phase:plan", None, "", 42, {"foo": "bar"}, "phase:replan"]}
        })
        assert result == ("phase:plan", "phase:replan")

    def test_empty_string_filtered(self):
        result = self._extract_and_call({"regions": {"declare": ["", "  "]}})
        assert result == ()


class TestProfileSourceRegionsDeclareField:
    """ProfileSource carries regions_declare as a frozen tuple."""

    def test_profile_source_has_regions_declare_field(self):
        """ProfileSource dataclass must carry regions_declare: tuple[str, ...] = ()"""
        f = pathlib.Path("lca/harness/profile/resolve/source.py")
        text = f.read_text(encoding="utf-8")
        # The ProfileSource dataclass should declare regions_declare
        assert "regions_declare: tuple[str, ...] = ()" in text, (
            "ProfileSource must carry regions_declare: tuple[str, ...] = () field"
        )

    def test_programmatic_profile_source_sets_regions_declare(self):
        """programmatic_profile_source() must pass regions_declare=() in its return."""
        f = pathlib.Path("lca/harness/profile/resolve/source.py")
        text = f.read_text(encoding="utf-8")
        # The programmatic factory's ProfileSource construction must include
        # regions_declare=() in the kwargs
        assert "regions_declare=()" in text, (
            "programmatic_profile_source must explicitly set regions_declare=()"
        )


class TestClosedSetAcceptsProfileRegions:
    """build_region_closed_set accepts profile.regions.declare."""

    def test_6_stage_plus_bare_plus_custom(self):
        from agent_lab.profile_loader import build_region_closed_set
        closed = build_region_closed_set({"phase:plan", "phase:replan", "control:safety"})
        # Builtin 6-stage
        for stage in ("perceive", "think", "act", "reflect", "remember", "stop"):
            assert f"phase:{stage}" in closed
        # Bare-enum
        for region in ("model_visible", "effect", "lineage", "digest", "control"):
            assert region in closed
        # Custom
        for region in ("phase:plan", "phase:replan", "control:safety"):
            assert region in closed

    def test_load_profile_regions_reads_web_assistant(self):
        """load_profile_regions(web-assistant) returns the 3 declared regions."""
        from agent_lab.profile_loader import load_profile_regions
        result = load_profile_regions("profiles/web-assistant.yaml")
        assert result == set(REGIONS_DECLARED), (
            f"web-assistant regions.declare must be {set(REGIONS_DECLARED)}, got {result}"
        )


class TestC14AcceptsProfileExtendedRegions:
    """The C14 validator accepts custom regions declared by the profile."""

    def test_phase_plan_spec_valid_against_web_assistant(self):
        """A spec with phase=plan is valid under web-assistant's closed set."""
        from agent_lab.graph.spec import InfoEdgeSpec, NodeRegion
        from agent_lab.graph.validate import validate_with_profile
        from agent_lab.profile_loader import build_region_closed_set, load_profile_regions

        spec = InfoEdgeSpec(
            id="plan_test",
            version="0.1.0",
            region=NodeRegion.PHASE,
            description="",
            phase="plan",  # custom region, not in 6-stage set
            nodes=[],
            edges=[],
            grants=[],
            sub_specs=[],
            plugins=[],
            discard_sink=None,
        )
        profile_regions = load_profile_regions("profiles/web-assistant.yaml")
        closed = build_region_closed_set(profile_regions)
        # The spec's region label is "phase:plan" — must be in the
        # web-assistant-extended closed set.
        assert "phase:plan" in closed
        # The validator should not raise C14 for this spec.
        from agent_lab.graph.spec import current_region_label
        assert current_region_label(spec) == "phase:plan"
        errs = validate_with_profile(spec, profile_regions=profile_regions)
        c14 = [e for e in errs if e.startswith("C14:")]
        assert c14 == [], f"unexpected C14 errors: {c14}"

    def test_unknown_region_still_fails_under_web_assistant(self):
        """A spec with region='phase:totally_made_up' fails C14 even with web-assistant."""
        from agent_lab.graph.spec import InfoEdgeSpec, NodeRegion
        from agent_lab.graph.validate import validate_with_profile
        from agent_lab.profile_loader import load_profile_regions

        spec = InfoEdgeSpec(
            id="bogus",
            version="0.1.0",
            region=NodeRegion.PHASE,
            description="",
            phase="totally_made_up",
            nodes=[],
            edges=[],
            grants=[],
            sub_specs=[],
            plugins=[],
            discard_sink=None,
        )
        profile_regions = load_profile_regions("profiles/web-assistant.yaml")
        errs = validate_with_profile(spec, profile_regions=profile_regions)
        c14 = [e for e in errs if e.startswith("C14:")]
        assert len(c14) == 1
        assert "phase:totally_made_up" in c14[0]
        assert "'bogus'" in c14[0]


# ---------------------------------------------------------------------------
# Verify the 3 declared regions are NOT in the lab.* capability closed set
# (P7-I-2: region labels do NOT participate in capability closure)
# ---------------------------------------------------------------------------

class TestRegionNotInLabCapabilityClosedSet:
    """The 3 declared regions (phase:plan, phase:replan, control:safety) must
    NOT appear in the lab.* capability closed set in capability-closed-set.md
    (P7-I-2 — region labels are observation dimensions, not capability
    dimensions)."""

    def test_regions_not_in_capability_spec(self):
        f = pathlib.Path("docs/specs/capability-closed-set.md")
        if not f.exists():
            pytest.skip("capability-closed-set.md not in this checkout")
        text = f.read_text(encoding="utf-8")
        import re
        # Extract the closed set list (between ```text ``` fences)
        m = re.search(r"```text\n(.*?)```", text, re.DOTALL)
        assert m, "no fenced closed set in spec"
        closed = m.group(1)
        # The 3 declared regions must NOT appear as lab.* keys
        for region in REGIONS_DECLARED:
            # The closed set has no `region:`, no `phase:plan` etc. as a
            # capability key.
            assert f'"{region}"' not in closed, (
                f"region {region!r} leaked into lab.* capability closed set "
                f"(P7-I-2 violation)"
            )