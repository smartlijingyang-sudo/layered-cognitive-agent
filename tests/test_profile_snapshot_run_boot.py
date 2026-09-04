import json
from pathlib import Path

from lca.plugins.observability.profile_snapshot_run_boot_provider import RunBootSnapshot


def test_run_boot_writes_snapshot(tmp_path: Path):
    snapshot = RunBootSnapshot()
    out = snapshot.write(
        run_id="r1",
        outdir=tmp_path,
        plan_ref="plan-hash-abc",
        plugins=[
            {
                "id": "lca-llm",
                "layer": "L2",
                "kind": "provider",
                "effects": ("llm", "network"),
            },
            {
                "id": "lca-tools",
                "layer": "L2",
                "kind": "provider",
                "effects": ("filesystem",),
            },
            {
                "id": "lca-journal-schema-v2",
                "layer": "L1",
                "kind": "seam",
                "effects": (),
            },
        ],
        capabilities={"lca-llm": True, "lca-tools": True, "lca-journal-schema-v2": True},
        control_plan={"version": "v3", "phases": ["perceive", "think", "gate", "act", "reflect"]},
    )
    assert out.exists()
    assert out.name == "profile_snapshot.json"
    data = json.loads(out.read_text())
    assert data["run_id"] == "r1"
    plugin_ids = {entry["id"] for entry in data["plugins"]}
    assert "lca-journal-schema-v2" in plugin_ids
    assert data["capabilities"]["lca-llm"] is True
    # P3 slim:plugins[] 是 dict 列表,且只含 {id, layer, kind, effects}
    for entry in data["plugins"]:
        assert set(entry.keys()) == {"id", "layer", "kind", "effects"}


def test_run_boot_creates_outdir_if_missing(tmp_path: Path):
    snapshot = RunBootSnapshot()
    nested = tmp_path / "traces" / "runs" / "r1"
    out = snapshot.write(
        run_id="r1",
        outdir=nested,
        plan_ref="",
        plugins=[],
        capabilities={},
        control_plan={},
    )
    assert nested.exists()
    assert out.exists()


def test_run_boot_handles_empty_collections(tmp_path: Path):
    snapshot = RunBootSnapshot()
    out = snapshot.write(
        run_id="empty-run",
        outdir=tmp_path,
        plan_ref="",
        plugins=[],
        capabilities={},
        control_plan={},
    )
    data = json.loads(out.read_text())
    assert data["plugins"] == []
    assert data["capabilities"] == {}
    assert data["control_plan"] == {}
