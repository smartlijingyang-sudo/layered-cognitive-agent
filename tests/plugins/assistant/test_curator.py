"""Tests for the procedural-memory curator (ADR-0244 D6.2)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from lca.contracts.models.core.state.lifecycle import TaskStatus
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
)
from lca.plugins.assistant.curator.curator import (
    ProceduralCurator,
    build_skill_md,
    extract_procedural_candidate,
)


def _budget() -> RuntimeBudgetSnapshot:
    return RuntimeBudgetSnapshot(
        max_tokens=1000,
        max_cost_usd=None,
        max_steps=10,
        max_wall_clock_seconds=60,
        used_tokens=10,
        used_cost_usd=0.0,
        used_steps=1,
    )


def _event(run_id: str, type_: RuntimeLifecycleEventType) -> RuntimeLifecycleEvent:
    return RuntimeLifecycleEvent(
        type=type_,
        trace_id=run_id,
        plan_ref="plan://test",
        status=TaskStatus.COMPLETED,
        step=1,
        budget=_budget(),
        state_ref=f"state:{run_id}",
        journal_sequence=3,
    )


def _write_spine(run_dir: Path, run_id: str, *, with_candidate: bool) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    events: list[dict[str, Any]] = []
    if with_candidate:
        events.append(
            {
                "execution_point": "phase_graph.node.end",
                "payload": {
                    "node_id": "reflect.score",
                    "output": {
                        "reflection": {
                            "extra": {
                                "procedural_candidate": {
                                    "candidate_id": "cand_run",
                                    "workflow_summary": "Two-step pipeline",
                                    "tool_sequence": ["fetch", "process"],
                                    "evidence_count": 2,
                                    "confidence": 0.9,
                                }
                            }
                        }
                    },
                },
            }
        )
    events.append({"execution_point": "kernel.run.stop", "payload": {"outcome": "success"}})
    with (run_dir / f"{run_id}.spine.jsonl").open("w", encoding="utf-8") as f:
        for _i, ev in enumerate(events):
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


class _FakeOverlay:
    def __init__(self) -> None:
        self.installs: list[tuple[str, Any, str]] = []

    async def install(self, assistant_id: str, source: Any, actor: str = "agent") -> Any:
        self.installs.append((assistant_id, source, actor))
        return SimpleNamespace(skill_id="procedural-test", install_path="")


def test_extract_procedural_candidate_from_spine(tmp_path: Path) -> None:
    run_id = "run_cand"
    run_dir = tmp_path / "traces" / "runs" / run_id
    _write_spine(run_dir, run_id, with_candidate=True)

    candidate = extract_procedural_candidate(run_dir)

    assert candidate is not None
    assert candidate["workflow_summary"] == "Two-step pipeline"
    assert candidate["tool_sequence"] == ["fetch", "process"]


def test_extract_procedural_candidate_absent(tmp_path: Path) -> None:
    run_id = "run_plain"
    run_dir = tmp_path / "traces" / "runs" / run_id
    _write_spine(run_dir, run_id, with_candidate=False)

    assert extract_procedural_candidate(run_dir) is None


def test_build_skill_md_has_frontmatter() -> None:
    md = build_skill_md(
        {"workflow_summary": "Data pipeline", "tool_sequence": ["fetch", "plot"]}, "run_abc12345"
    )
    assert "name: procedural-abc12345" in md
    assert "description: Data pipeline." in md
    assert "1. fetch" in md
    assert "2. plot" in md


async def test_publish_writes_proposal_on_terminal(tmp_path: Path) -> None:
    run_id = "run_propose"
    run_dir = tmp_path / "traces" / "runs" / run_id
    _write_spine(run_dir, run_id, with_candidate=True)
    curator = ProceduralCurator(overlay=_FakeOverlay(), traces_root=tmp_path / "traces" / "runs")

    await curator.publish(_event(run_id, RuntimeLifecycleEventType.COMPLETED))

    proposal_path = run_dir / "curator_proposal.json"
    assert proposal_path.is_file()
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    assert proposal["status"] == "proposed"
    assert proposal["candidate"]["workflow_summary"] == "Two-step pipeline"


async def test_publish_skips_non_terminal(tmp_path: Path) -> None:
    run_id = "run_skip"
    run_dir = tmp_path / "traces" / "runs" / run_id
    _write_spine(run_dir, run_id, with_candidate=True)
    curator = ProceduralCurator(overlay=_FakeOverlay(), traces_root=tmp_path / "traces" / "runs")

    await curator.publish(_event(run_id, RuntimeLifecycleEventType.STARTED))

    assert not (run_dir / "curator_proposal.json").exists()


async def test_publish_skips_without_candidate(tmp_path: Path) -> None:
    run_id = "run_no_cand"
    run_dir = tmp_path / "traces" / "runs" / run_id
    _write_spine(run_dir, run_id, with_candidate=False)
    curator = ProceduralCurator(overlay=_FakeOverlay(), traces_root=tmp_path / "traces" / "runs")

    await curator.publish(_event(run_id, RuntimeLifecycleEventType.COMPLETED))

    assert not (run_dir / "curator_proposal.json").exists()


async def test_confirm_installs_skill_and_marks_confirmed(tmp_path: Path) -> None:
    run_id = "run_confirm"
    run_dir = tmp_path / "traces" / "runs" / run_id
    _write_spine(run_dir, run_id, with_candidate=True)
    overlay = _FakeOverlay()
    curator = ProceduralCurator(overlay=overlay, traces_root=tmp_path / "traces" / "runs")

    await curator.publish(_event(run_id, RuntimeLifecycleEventType.COMPLETED))
    receipt = await curator.confirm("asst_1", run_id)

    assert receipt is not None
    assert receipt.skill_id == "procedural-test"
    assert len(overlay.installs) == 1
    assert overlay.installs[0][0] == "asst_1"
    assert (run_dir / "curator_proposal.confirmed.json").is_file()
    assert not (run_dir / ".curator-staging").exists()


async def test_confirm_idempotent(tmp_path: Path) -> None:
    run_id = "run_idem"
    run_dir = tmp_path / "traces" / "runs" / run_id
    _write_spine(run_dir, run_id, with_candidate=True)
    overlay = _FakeOverlay()
    curator = ProceduralCurator(overlay=overlay, traces_root=tmp_path / "traces" / "runs")

    await curator.publish(_event(run_id, RuntimeLifecycleEventType.COMPLETED))
    first = await curator.confirm("asst_1", run_id)
    second = await curator.confirm("asst_1", run_id)

    assert first is not None
    assert second is None
    assert len(overlay.installs) == 1


async def test_confirm_without_proposal_returns_none(tmp_path: Path) -> None:
    run_id = "run_no_proposal"
    curator = ProceduralCurator(overlay=_FakeOverlay(), traces_root=tmp_path / "traces" / "runs")

    receipt = await curator.confirm("asst_1", run_id)

    assert receipt is None
