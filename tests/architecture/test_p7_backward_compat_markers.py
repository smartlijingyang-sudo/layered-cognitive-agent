"""ADR-0210 §6.5 — backward-compat marker audit tests.

Verifies that the 0075/0194 backward-compat items carry explicit
deprecation markers pointing to the P7 region-tag path:

  - CognitivePhaseGraphPlan class docstring
  - PhaseBinding class docstring
  - declarative-phase-graph.yaml bundle header
  - agent_lab/plugins/base.py (hook helper re-export shim)
  - agent_lab/plugins/__init__.py (no stale GraphPlugin re-export)

These markers make the 0075/0194 path's status explicit (Optional +
backward-compat, NOT SSOT) and point to the recommended P7 path
(region tags + profile.regions.declare).
"""

import pathlib

import yaml


# ---------------------------------------------------------------------------
# CognitivePhaseGraphPlan
# ---------------------------------------------------------------------------

class TestCognitivePhaseGraphPlanDeprecation:
    """CognitivePhaseGraphPlan carries a .. deprecated:: marker (ADR-0210 §6.5)."""

    def test_docstring_has_deprecated_marker(self):
        f = (
            pathlib.Path(
                "lca/contracts/protocols/declarative/declarative_1/declarative_graph.py"
            )
        )
        text = f.read_text(encoding="utf-8")
        # Find the CognitivePhaseGraphPlan class block
        start = text.find("class CognitivePhaseGraphPlan")
        assert start >= 0
        # Search within the docstring (next ~50 lines)
        block = text[start : start + 1500]
        assert ".. deprecated::" in block, (
            "CognitivePhaseGraphPlan must carry a .. deprecated:: marker "
            "(ADR-0210 §6.5)"
        )
        # The marker must point to the P7 region-tag path
        assert "region-tag" in block or "region tag" in block or "P7" in block, (
            "deprecation marker must point to the P7 region-tag path"
        )


# ---------------------------------------------------------------------------
# PhaseBinding
# ---------------------------------------------------------------------------

class TestPhaseBindingDeprecation:
    """PhaseBinding carries a .. deprecated:: marker on semantic_phase."""

    def test_docstring_has_deprecated_marker(self):
        f = (
            pathlib.Path(
                "lca/contracts/protocols/declarative/declarative_1/declarative_graph.py"
            )
        )
        text = f.read_text(encoding="utf-8")
        start = text.find("class PhaseBinding")
        assert start >= 0
        block = text[start : start + 1500]
        assert ".. deprecated::" in block, (
            "PhaseBinding must carry a .. deprecated:: marker "
            "(ADR-0210 §6.5 — semantic_phase field is retained for backward compat)"
        )
        assert "semantic_phase" in block, (
            "deprecation must mention semantic_phase field"
        )


# ---------------------------------------------------------------------------
# declarative-phase-graph.yaml bundle header
# ---------------------------------------------------------------------------

class TestDeclarativePhaseGraphBundleHeader:
    """declarative-phase-graph.yaml header carries a .. note:: deprecation."""

    def test_yaml_has_deprecation_note(self):
        f = pathlib.Path("bundles/declarative-phase-graph.yaml")
        data = yaml.safe_load(f.read_text(encoding="utf-8"))
        # Re-read the raw text to check for the comment
        text = f.read_text(encoding="utf-8")
        # Comment lines start with #
        comment_block = "\n".join(
            line for line in text.splitlines() if line.startswith("#")
        )
        assert "Backward-compat" in comment_block or "P7" in comment_block, (
            "declarative-phase-graph.yaml header must signal backward-compat / P7"
        )
        # Sanity: bundle still parses with the entries list
        assert "entries" in data, (
            f"bundle parse sanity: missing 'entries', got keys: {list(data.keys())!r}"
        )
        assert len(data["entries"]) >= 1, (
            "bundle should declare at least one phase entry"
        )


# ---------------------------------------------------------------------------
# agent_lab.plugins.base (hook helper re-export shim)
# ---------------------------------------------------------------------------

class TestAgentLabPluginsBaseShim:
    """agent_lab/plugins/base.py is a thin compat shim (no GraphPlugin / no register_plugin)."""

    def test_base_no_graphplugin(self):
        f = pathlib.Path("agent_lab/plugins/base.py")
        text = f.read_text(encoding="utf-8")
        # No GraphPlugin class body in the shim
        assert "class GraphPlugin" not in text, (
            "base.py must not define GraphPlugin (moved to lca.plugins.lab.internal.hooks)"
        )
        # No register_plugin function
        assert "def register_plugin" not in text, (
            "base.py must not define register_plugin (deleted in PR-D final)"
        )
        # Has the deprecation marker
        assert ".. deprecated::" in text, (
            "base.py must carry a .. deprecated:: marker (ADR-0210 §6.5)"
        )
        # The shim re-exports the 4 hook helpers
        for sym in ("Bind", "HookContext", "HookEvent", "fanout_hooks"):
            assert sym in text, f"base.py must re-export {sym}"

    def test_base_all_exports_match(self):
        """The shim's __all__ is exactly the 4 hook helpers (no leak)."""
        f = pathlib.Path("agent_lab/plugins/base.py")
        text = f.read_text(encoding="utf-8")
        # Find __all__ block
        start = text.find("__all__")
        end = text.find("]", start)
        block = text[start : end + 1]
        assert "Bind" in block and "HookContext" in block
        assert "HookEvent" in block and "fanout_hooks" in block
        # No GraphPlugin or register_plugin
        assert "GraphPlugin" not in block
        assert "register_plugin" not in block


# ---------------------------------------------------------------------------
# agent_lab.plugins.__init__ (no stale GraphPlugin re-export)
# ---------------------------------------------------------------------------

class TestAgentLabPluginsInitClean:
    """agent_lab/plugins/__init__.py must not re-export GraphPlugin (deleted)."""

    def test_init_no_graphplugin(self):
        f = pathlib.Path("agent_lab/plugins/__init__.py")
        text = f.read_text(encoding="utf-8")
        # __all__ block must not include GraphPlugin
        start = text.find("__all__")
        end = text.find("]", start)
        block = text[start : end + 1]
        assert "GraphPlugin" not in block, (
            "agent_lab/plugins/__init__.py must not re-export GraphPlugin "
            "(PR-D final 1/2 + ADR-0210 §6.5)"
        )
        # The 4 hook helpers remain
        for sym in ("Bind", "HookContext", "HookEvent", "fanout_hooks"):
            assert sym in block, f"__init__.py must re-export {sym}"


# ---------------------------------------------------------------------------
# Cross-reference: P7 path is the recommended way
# ---------------------------------------------------------------------------

class TestP7PathDocumentedAsRecommended:
    """The P7 region-tag path is documented as the recommended runtime."""

    def test_cognitive_phase_graph_plan_points_to_p7(self):
        f = (
            pathlib.Path(
                "lca/contracts/protocols/declarative/declarative_1/declarative_graph.py"
            )
        )
        text = f.read_text(encoding="utf-8")
        # The deprecation note for CognitivePhaseGraphPlan should mention
        # either "P7", "region-tag", "region tag", or the helper file
        assert any(
            token in text
            for token in ("P7", "region-tag", "region tag", "build_region_only_phase_graph")
        ), (
            "CognitivePhaseGraphPlan deprecation must reference P7 region-tag path"
        )

    def test_phase_binding_points_to_p7(self):
        f = (
            pathlib.Path(
                "lca/contracts/protocols/declarative/declarative_1/declarative_graph.py"
            )
        )
        text = f.read_text(encoding="utf-8")
        # Look for P7/region-tag references in or near the PhaseBinding deprecation
        # marker
        start = text.find("class PhaseBinding")
        block = text[start : start + 1500]
        assert any(
            token in block
            for token in ("P7", "region-tag", "region tag", "P7-I-2")
        ), "PhaseBinding deprecation must reference the P7 region-tag path"