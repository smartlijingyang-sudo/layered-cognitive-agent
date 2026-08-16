"""result_preview / arguments_preview are jsonl+OTel only.

Live UI and the LLM prompt must not read them. Allowed production paths
are an allowlist — a new reader fails CI.
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolInvoked,
)
from lca.layer0_infra.observability.journal.journal_io import stamped_to_record
from lca.layer0_infra.observability.journal.sse_frames import stamped_to_sse_frame

_ROOT = Path(__file__).resolve().parent.parent

_PREVIEW_ALLOWLIST = {
    "lca/contracts/models/observability/journal.py",
    "lca/layer1_cognitive/body/safe_executor.py",
    "lca/layer1_cognitive/body/pipeline_safe_executor.py",
    "lca/layer1_cognitive/body/tool_result_preview.py",
    "lca/layer1_cognitive/body/tool_ui_state.py",
    "lca/layer0_infra/observability/journal/otel_mapping.py",
    "lca/layer0_infra/observability/journal/sse_frames.py",
    "lca/layer0_infra/observability/journal/fact_stream_projector.py",
    "lca/layer0_infra/dsh/projector.py",
}


def test_result_preview_has_no_new_production_readers() -> None:
    offenders: list[str] = []
    for path in (*(_ROOT / "lca").rglob("*.py"), *(_ROOT / "deploy").rglob("*.ts")):
        rel = str(path.relative_to(_ROOT))
        if rel in _PREVIEW_ALLOWLIST:
            continue
        if "result_preview" in path.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert offenders == [], "result_preview leaked outside allowlist:\n" + "\n".join(offenders)


def test_driver_never_names_result_preview() -> None:
    driver = (_ROOT / "deploy/lobehub/patches/runtime/LcaRunDriver.ts").read_text(encoding="utf-8")
    journal = (_ROOT / "deploy/lobehub/patches/runtime/lcaJournal.ts").read_text(encoding="utf-8")
    assert "result_preview" not in driver
    assert "result_preview" not in journal


def test_live_sse_redacts_previews_keeps_plugin_state() -> None:
    state = {"content": "# officecli", "success": True}
    stamped = StampedEvent(
        seq=3,
        ts=1.0,
        scope=RunScope(trace_id="t", run_id="r"),
        event=ToolInvoked(
            tool_name="activate_skill",
            arguments_preview='{"skill_id":"officecli"}',
            result_preview='{"text":"# officecli","skill_id":"officecli"}',
            plugin_state=state,
        ),
    )
    jsonl = stamped_to_record(stamped)
    assert jsonl["event"]["result_preview"].startswith("{")
    assert jsonl["event"]["arguments_preview"]

    frame = stamped_to_sse_frame(stamped)
    live = json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))
    assert live["event"]["result_preview"] == ""
    assert live["event"]["arguments_preview"] == ""
    assert live["event"]["plugin_state"] == state
