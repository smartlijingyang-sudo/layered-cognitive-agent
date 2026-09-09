# PR-D final 2/2 — real @plugin carrier tests
"""Tests verifying that the generated LabCarrier files act as real
LCA-plugin-compatible carriers (without requiring cordis at import).

The generator in ``scripts/generate_lab_carriers.py`` emits 88 carrier
files; these tests sample a representative subset to verify:

1. Each carrier registers a marker in ``_LAB_HOOKS`` at import time
   (auto-bind via ``bind_carrier(_CARRIER)``).
2. The marker carries the right shape (id / stage / kind / provides /
   requires / inputs / outputs).
3. The marker's ``node_id`` matches the basename of the slot id.
4. The marker's ``module`` / ``class`` fields point at the legacy
   implementation for lazy import.
5. The carrier provides a ``setup(ctx, config)`` entry point that
   re-binds (for two-phase boot).
6. Generating carriers is idempotent (re-running the generator
   doesn't break the loader).
"""

import importlib
import pathlib
import subprocess
import sys

import pytest

from lca.plugins.lab.internal.loader import (
    _LAB_HOOKS,
    get_instance,
    list_ids,
    load_all,
    reset_for_tests,
)


# Sample of representative carriers across every phase.
REPRESENTATIVE_SLOTS = (
    "lab.perceive.sense",
    "lab.perceive.commit",
    "lab.think.expose",
    "lab.think.reason",
    "lab.think.guard",
    "lab.reflect.critique",
    "lab.reflect.join",
    "lab.remember.admit",
    "lab.remember.snapshot",
    "lab.control.barrier",
    "lab.control.act_execute_node",
    "lab.control.observe_checkpoint",
    "lab.session_log.append_node_start",
    "lab.session_log.append_edge_fire",
    "lab.session_log.fold_header",
    "lab.lineage.trace_node_start",
    "lab.lineage.trace_subgraph_exit",
    "lab.event.emit",
    "lab.event.tail",
    "lab.llm.call_llm",
    "lab.llm.commit_manifest",
    "lab.model_eye.see",
    "lab.model_eye.freeze",
    "lab.model_visible.prompt_assemble",
    "lab.model_visible.history_attach",
    "lab.passthrough.identity",
    "lab.passthrough.dedup_v2",
    "lab.tool.expose_schemas",
    "lab.tool.grant_check",
)


class TestCarrierAutoBind:
    """Generated carriers must auto-register on import."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_load_all_finds_all_carriers(self):
        load_all()
        ids = list_ids()
        # 88 generated carriers + 4 hook plugins + 4 act workers +
        # 4 providers + 1 session + 1 tools = 102 total
        assert len(ids) >= 88, f"expected >= 88 carrier markers, got {len(ids)}"

    def test_representative_carriers_registered(self):
        load_all()
        ids = set(list_ids())
        for slot in REPRESENTATIVE_SLOTS:
            assert slot in ids, (
                f"carrier {slot} not registered; got ids={sorted(ids)[:5]}..."
            )


class TestCarrierMarkerShape:
    """Each carrier's marker must carry the right shape."""

    def setup_method(self):
        reset_for_tests()
        load_all()

    def teardown_method(self):
        reset_for_tests()

    @pytest.mark.parametrize("slot", list(REPRESENTATIVE_SLOTS))
    def test_marker_has_required_keys(self, slot):
        marker = get_instance(slot)
        assert marker is not None, f"{slot} missing"
        for key in ("id", "stage", "kind", "module", "class", "provides", "requires"):
            assert key in marker, f"{slot} missing {key!r}"

    @pytest.mark.parametrize("slot", list(REPRESENTATIVE_SLOTS))
    def test_marker_node_id_matches_slot_basename(self, slot):
        marker = get_instance(slot)
        basename = slot.rsplit(".", 1)[-1]
        assert marker["id"] == basename, (
            f"{slot}: marker['id']={marker['id']!r} should equal basename={basename!r}"
        )

    def test_perceive_sense_carries_capability_closure(self):
        """perceive.sense is a typed transformer — must carry provides/requires."""
        marker = get_instance("lab.perceive.sense")
        assert marker["provides"] == ["sensor_items"]
        assert marker["requires"] == ["sensors"]
        assert marker["emits"] == ["sensor_items"]
        # out_capability key must be present
        assert "lab.perceive.sense.out:sensor_items" in marker["out_capabilities"]


class TestCarrierSetupEntry:
    """Each carrier exposes setup(ctx, config) for two-phase boot."""

    def setup_method(self):
        reset_for_tests()
        load_all()

    def teardown_method(self):
        reset_for_tests()

    def test_perceive_sense_has_setup(self):
        import lca.plugins.lab.perceive.sense.plugin as m
        assert callable(m.setup), "perceive.sense must expose setup()"
        # setup() must be idempotent — calling it again must not raise
        m.setup(None, None)
        # _LAB_HOOKS still has the slot
        assert "lab.perceive.sense" in _LAB_HOOKS

    def test_think_reason_has_setup(self):
        import lca.plugins.lab.think.reason.plugin as m
        assert callable(m.setup)
        m.setup(None, None)


class TestCarrierModuleClass:
    """Carrier's source_module / source_class must point at the legacy
    implementation (so a real Cordis boot can lazy-import the real
    implementation when needed)."""

    def setup_method(self):
        reset_for_tests()
        load_all()

    def teardown_method(self):
        reset_for_tests()

    def test_perceive_sense_module_path(self):
        marker = get_instance("lab.perceive.sense")
        assert marker["module"] == "agent_lab.nodes.perceive.sense.plugin"
        assert marker["class"] == "PerceiveSense"

    def test_session_log_emitter_shared_class(self):
        """All session_log.append_* carriers share the same source class
        (SessionLogEmitterPlugin) — the carrier is a per-event thin wrapper."""
        for slot in (
            "lab.session_log.append_node_start",
            "lab.session_log.append_edge_fire",
            "lab.session_log.fold_header",
        ):
            marker = get_instance(slot)
            assert marker["class"] == "SessionLogEmitterPlugin", (
                f"{slot}: expected SessionLogEmitterPlugin, got {marker['class']}"
            )


class TestGenerationIdempotence:
    """The generator must be re-runnable without breaking the loader."""

    def test_generator_runs_clean(self):
        result = subprocess.run(
            ["python3", "scripts/generate_lab_carriers.py"],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"generator failed: {result.stderr}"
        )
        assert "Generated" in result.stdout

    def test_carrier_count_after_regeneration(self):
        """After re-generation, the marker count must be stable."""
        before = len(list_ids())
        load_all()
        before = len(list_ids())
        # Re-run generator
        subprocess.run(
            ["python3", "scripts/generate_lab_carriers.py"],
            check=True
        )
        # Reset and reload — should give the same count
        reset_for_tests()
        load_all()
        after = len(list_ids())
        assert after == before, (
            f"marker count changed: before={before}, after={after}"
        )