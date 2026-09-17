"""ADR-0210 §6.6 — real production profile verification tests.

Verifies that ``profiles/web-assistant.yaml`` declares the P7
region-tag closed set extension via ``regions.declare``:

  - phase:plan
  - phase:replan
  - control:safety

``lca.harness.profile.resolve.source`` parses the section into
``ProfileSource.regions_declare`` as an immutable tuple.
"""

import pathlib

import yaml


REGIONS_DECLARED = ("phase:plan", "phase:replan", "control:safety")

PROFILES = pathlib.Path("profiles")
WEB_STANDARD = PROFILES / "web-standard.yaml"
WEB_ASSISTANT = PROFILES / "web-assistant.yaml"


class TestWebAssistantRegionsDeclared:
    """The web-assistant profile must declare the 3 P7 custom regions."""

    def test_yaml_is_valid(self):
        f = pathlib.Path("profiles/web-assistant.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"profile parse failed: {data!r}"
        assert "regions" in data, "web-assistant.yaml must declare 'regions:' (ADR-0210 §6.6)"

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
        result = self._extract_and_call({"regions": {"declare": ["phase:plan", "phase:replan"]}})
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
        result = self._extract_and_call(
            {"regions": {"declare": ["phase:plan", None, "", 42, {"foo": "bar"}, "phase:replan"]}}
        )
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


class TestWebAssistantOnP7Path:
    """web-assistant.yaml now runs the P7 region-tag path
    (declarative-phase-graph.yaml removed; the 3 custom regions
    are the closed-set extension)."""

    def test_no_0075_phase_topology_bundle(self):
        f = pathlib.Path("profiles/web-assistant.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert "bundles/declarative-phase-graph.yaml" not in data["bundles"], (
            "web-assistant.yaml must not load declarative-phase-graph.yaml "
            "(0075 phase_graph SSOT path); the P7 region-tag path is the "
            "recommended runtime per ADR-0210 §6.6"
        )

    def test_regions_declare_still_there(self):
        f = pathlib.Path("profiles/web-assistant.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert "regions" in data, "regions: section must remain (ADR-0210 §6.6)"
        assert data["regions"]["declare"] == list(REGIONS_DECLARED), (
            "regions.declare must still be phase:plan / phase:replan / "
            "control:safety for the P7 path"
        )

    def test_bundle_set(self):
        """web-assistant 的 bundles = web-standard 的列表(同序)+ 助理域两条。

        bundle 不只带 plugin entry,还带 plan 拓扑(outer/phase_main + phase
        subgraph)与观测面;少一条,run 在 plan lift 或运维命令上失败,而
        resolve 出的 plugin 集看不出来。
        """
        standard = yaml.safe_load(WEB_STANDARD.read_text(encoding="utf-8"))["bundles"]
        assistant = yaml.safe_load(WEB_ASSISTANT.read_text(encoding="utf-8"))["bundles"]
        assert assistant[: len(standard)] == standard, (
            f"web-assistant 前 {len(standard)} 条 bundle 必须与 web-standard 同序一致;"
            f"实际:{assistant}"
        )
        assert set(assistant[len(standard) :]) == {
            "bundles/assistant-runtime.yaml",
            "bundles/composio-tools.yaml",
        }, f"助理域增量 bundle 漂移:{assistant[len(standard) :]}"

    def test_docstring_documents_p7_path(self):
        """The header docstring must explain the P7 switch."""
        f = pathlib.Path("profiles/web-assistant.yaml")
        text = f.read_text(encoding="utf-8")
        assert "P7 region-tag path" in text or "P7 path" in text, (
            "web-assistant.yaml header must document the P7 region-tag switch"
        )
