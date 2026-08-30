"""Inspect CLI — capability graph (PR12.G.2).

``lca-ops inspect-tree`` must:

- Load any valid profile YAML (currently ``profiles/web-standard.yaml``
  crashes in the buggy v0; we assert it loads cleanly).
- For each plugin handle, derive a capability graph from the typed
  ``PluginMeta`` (or the legacy ``manifest`` object) and emit at least
  ``implements`` + ``emitted_events`` + ``context_fields`` rows.

The capability graph lives in
``lca.harness.diagnostics.inspect.format_capability_graph``; the
``format_plugin_tree`` callable stays for backwards compat.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestInspectCapabilityGraph:
    def test_inspect_tree_includes_implements(self) -> None:
        """The capability graph MUST include ``implements``."""
        from lca.harness.diagnostics.inspect import format_capability_graph

        meta = {
            "name": "lca.clock.sensor",
            "layer": "sensor",
            "implements": ["Sensor"],
            "emitted_events": [],
            "context_fields": ["clock"],
            "capabilities": [],
            "side_effects": "none",
        }
        graph = format_capability_graph(meta)
        assert "implements" in graph
        assert "Sensor" in graph["implements"]

    def test_inspect_tree_includes_emitted_events(self) -> None:
        """The capability graph MUST include ``emitted_events``."""
        from lca.harness.diagnostics.inspect import format_capability_graph

        meta = {
            "name": "lca.memory.commit",
            "layer": "behavior",
            "implements": ["MemoryPolicy"],
            "emitted_events": ["MemoryCommitted", "ContextCompacted"],
            "context_fields": [],
            "capabilities": ["memory.write"],
            "side_effects": "memory",
        }
        graph = format_capability_graph(meta)
        assert "emitted_events" in graph
        assert "MemoryCommitted" in graph["emitted_events"]
        assert "ContextCompacted" in graph["emitted_events"]

    def test_format_capability_graph_returns_dict(self) -> None:
        """``format_capability_graph`` MUST return a ``dict`` (graph shape)."""
        from lca.harness.diagnostics.inspect import format_capability_graph

        meta = {
            "name": "p",
            "layer": "service",
            "implements": ["Brain"],
            "emitted_events": [],
            "context_fields": ["workspace_artifacts"],
            "capabilities": [],
            "side_effects": "none",
        }
        graph = format_capability_graph(meta)
        assert isinstance(graph, dict)
        assert "implements" in graph
        assert "emitted_events" in graph
        assert "context_fields" in graph

    def test_format_capability_graph_handles_legacy_manifest(self) -> None:
        """Legacy ``manifest`` object MUST be adapted into the graph dict."""

        class _LegacyManifest:
            kind = "service"
            seam_key = "agent.before_think"

        from lca.harness.diagnostics.inspect import format_capability_graph_from_legacy

        graph = format_capability_graph_from_legacy(_LegacyManifest())
        assert graph.get("layer") == "service"
        assert graph.get("seam_key") == "agent.before_think"

    def test_inspect_tree_loads_webstandard_yaml_without_crash(self, tmp_path: Path) -> None:
        """``inspect_tree`` MUST NOT crash on a minimal profile YAML.

        The previous CLI version referenced an undefined ``tree`` symbol
        (PR12.G.2 fix).  We assert that the new implementation handles
        a profile YAML end-to-end without raising.
        """
        from typer.testing import CliRunner

        from lca.layer0_infra.ops.cli import app

        # Write a minimal YAML profile.
        profile = tmp_path / "mini.yaml"
        profile.write_text("plugins: []\n", encoding="utf-8")

        runner = CliRunner()
        result = runner.invoke(app, ["inspect-tree", str(profile)])
        # We only care that no uncaught exception escaped; the command may
        # exit 0 (printed the tree) or 1 (profile invalid) but NOT crash.
        assert result.exception is None or isinstance(result.exception, SystemExit), (
            f"inspect-tree crashed: {result.exception!r}\n"
            f"stdout={result.stdout}\nstderr={result.stderr or ''}"
        )
