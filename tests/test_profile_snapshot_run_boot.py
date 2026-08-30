import json
from pathlib import Path

from lca.plugins.providers.profile_snapshot.run_boot import RunBootSnapshot


def test_run_boot_writes_snapshot(tmp_path: Path):
    snapshot = RunBootSnapshot()
    out = snapshot.write(
        run_id="r1",
        outdir=tmp_path,
        plan_ref="plan-hash-abc",
        plugins=["lca-llm", "lca-tools", "lca-journal-schema-v2"],
        capabilities={"llm": True, "tools": True, "journal_schemas": True},
        control_plan={"version": "v3", "phases": ["perceive", "think", "gate", "act", "reflect"]},
    )
    assert out.exists()
    assert out.name == "profile_snapshot.json"
    data = json.loads(out.read_text())
    assert data["run_id"] == "r1"
    assert "lca-journal-schema-v2" in data["plugins"]
    assert data["capabilities"]["llm"] is True


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
