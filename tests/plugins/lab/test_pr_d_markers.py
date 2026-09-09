# PR-D — full node plugin marker generation tests
"""Tests for PR-D's bulk node plugin marker generation.

PR-D registers stub markers for every remaining node factory under
``agent_lab.nodes.<area>.<name>`` so the loader knows about every
factory id. The actual node implementations stay in place until a
follow-up rewrites them as full @plugin carriers.
"""

import pathlib
import pytest
from lca.plugins.lab.internal.loader import (
    get_instance,
    list_ids,
    load_all,
    reset_for_tests,
)


EXPECTED_AREAS = (
    "perceive",
    "think",
    "reflect",
    "remember",
    "control",
    "llm",
    "model_eye",
    "model_visible",
    "lineage",
    "event",
    "passthrough",
    "tool",
    "session_log",
)


class TestPRDMarkerGeneration:
    """Verify the loader registers every PR-D node marker."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_load_all_includes_all_areas(self):
        """load_all() should register at least one marker per area."""
        load_all()
        ids = list_ids()
        for area in EXPECTED_AREAS:
            area_ids = [k for k in ids if k.startswith(f"lab.{area}.")]
            assert len(area_ids) >= 1, (
                f"area {area!r} has no markers; got ids={ids}"
            )

    def test_total_marker_count(self):
        """load_all() should register at least 90 markers (PR-A + PR-B + PR-C + PR-D)."""
        load_all()
        ids = list_ids()
        # PR-A.3: 9 hooks + PR-B: 7 act/providers + PR-C: 1 session + PR-D: ~89 nodes
        assert len(ids) >= 90, f"expected at least 90 markers, got {len(ids)}"

    def test_every_marker_has_id_field(self):
        """Every PR-D marker must be a dict with 'id' field."""
        load_all()
        ids = list_ids()
        # Spot check a few representative ones
        for marker_id in (
            "lab.perceive.sense",
            "lab.think.reason",
            "lab.reflect.critique",
            "lab.remember.admit",
            "lab.control.barrier",
            "lab.llm.call_llm",
            "lab.model_eye.see",
            "lab.model_visible.prompt_assemble",
            "lab.lineage.trace_edge_fire",
            "lab.event.emit",
            "lab.passthrough.identity",
            "lab.tool.expose_schemas",
            "lab.session_log.append_node_start",
        ):
            marker = get_instance(marker_id)
            assert marker is not None, f"missing marker {marker_id}"
            assert isinstance(marker, dict), (
                f"{marker_id} marker should be dict, got {type(marker)}"
            )
            assert "id" in marker, f"{marker_id} marker missing 'id' field"

    def test_every_marker_id_matches_slot(self):
        """Marker['id'] should match either the basename OR the full slot id
        (node markers use basename; provider markers use basename because
        the slot path's last segment is shared with other providers —
        e.g. 'tools.provider' and 'transport.provider' both end in 'provider').
        Non-dict markers (e.g. PR-A.3 hook plugin instances) are skipped."""
        load_all()
        ids = list_ids()
        for marker_id in ids:
            marker = get_instance(marker_id)
            # Skip non-dict markers (PR-A.3 hook plugins are class instances)
            if not isinstance(marker, dict):
                continue
            basename = marker_id.rsplit(".", 1)[-1]
            assert marker["id"] in (basename, marker_id), (
                f"{marker_id}: marker['id']={marker['id']!r} "
                f"should equal basename {basename!r} or slot {marker_id!r}"
            )


class TestPRDFilesystemCoverage:
    """Verify every node area has __init__.py + plugin.py."""

    def test_all_areas_have_init_and_plugin(self):
        for area in EXPECTED_AREAS:
            area_dir = pathlib.Path(f"lca/plugins/lab/{area}")
            assert area_dir.exists(), f"missing area dir: {area_dir}"
            assert (area_dir / "__init__.py").exists(), (
                f"missing {area_dir}/__init__.py"
            )
            # At least one plugin.py in subdir
            plugin_files = list(area_dir.glob("*/plugin.py"))
            assert len(plugin_files) >= 1, (
                f"{area} has no plugin.py in any subdir"
            )

    def test_old_agent_lab_node_dirs_still_present(self):
        """Old agent_lab.nodes dirs are untouched by PR-D (delete-when is PR-D final)."""
        for area in EXPECTED_AREAS:
            if area == "session_log":
                continue  # session_log already absorbed to lca.plugins.lab
            old = pathlib.Path(f"agent_lab/nodes/{area}")
            assert old.exists(), f"old dir unexpectedly missing: {old}"


class TestLoaderClosedSet:
    """Verify loader allow-list covers all PR-D plugin dirs."""

    def setup_method(self):
        reset_for_tests()

    def teardown_method(self):
        reset_for_tests()

    def test_known_subpackages_includes_pr_d_areas(self):
        """known_subpackages must include at least one plugin per PR-D area."""
        from lca.plugins.lab.internal.loader import known_subpackages
        known = set(known_subpackages())
        for area in EXPECTED_AREAS:
            area_pkgs = [k for k in known if f"lca.plugins.lab.{area}." in k]
            assert len(area_pkgs) >= 1, (
                f"loader allow-list missing {area} plugins"
            )