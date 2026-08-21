"""ADR-0065 §四 view-only boundary tests。

磁盘 v2 envelope 不含 ``*_preview`` / ``output_truncated`` / ``plugin_state``
view-only 字段(0065 §四 L1);typed fields 完整保留。Live SSE frame 与
disk record 共享同一 view-only stripping 路径;redact 参数仅保留
legacy ``_LIVE_REDACT_KEYS`` 兼容层。
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

# 允许含 ``*_preview`` 字符串的文件:声明保留 view-only 字段的契约 / emit
# 路径 / 迁移期工具。新增路径必须先经 PR 评审再加入 allowlist。
_PREVIEW_ALLOWLIST = {
    "lca/contracts/models/observability/journal.py",
    "lca/layer1_cognitive/body/safe_executor.py",
    "lca/layer1_cognitive/body/pipeline_safe_executor.py",
    "lca/layer1_cognitive/body/tool_result_preview.py",
    "lca/layer1_cognitive/body/tool_ui_state.py",
    "lca/layer1_cognitive/body/tool_journal_emit.py",
    "lca/layer0_infra/observability/journal/otel_mapping.py",
    "lca/layer0_infra/observability/journal/sse_frames.py",
    "lca/layer0_infra/observability/journal/journal_io.py",
    "lca/layer0_infra/observability/journal/fact_stream_projector.py",
}


def test_result_preview_has_no_new_production_readers() -> None:
    """任何路径都不能引用 ``result_preview`` 字符串,除非在 allowlist。"""
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


def test_disk_v2_envelope_strips_view_only_fields() -> None:
    """ADR-0065 §四: disk v2 envelope data 字段不含 view-only。"""
    state = {"content": "# officecli", "success": True}
    stamped = StampedEvent(
        seq=3,
        ts=1.0,
        scope=RunScope(trace_id="t", run_id="r"),
        event=ToolInvoked(
            tool_name="activate_skill",
            arguments_preview='{"skill_id":"officecli"}',
            result_preview='{"text":"# officecli","skill_id":"officecli"}',
            output_truncated=True,
            plugin_state=state,
            code="# officecli",
            language="markdown",
            skill_id="officecli",
            output_text="# officecli",
        ),
    )
    jsonl = stamped_to_record(stamped)
    data_keys = set(jsonl["data"].keys())
    # view-only 已剥离
    for forbidden in {"arguments_preview", "result_preview", "output_truncated", "plugin_state"}:
        assert forbidden not in data_keys, f"{forbidden} leaked to disk"
    # typed fields 完整保留
    assert jsonl["data"]["tool_name"] == "activate_skill"
    assert jsonl["data"]["code"] == "# officecli"
    assert jsonl["data"]["language"] == "markdown"
    assert jsonl["data"]["skill_id"] == "officecli"


def test_live_sse_keeps_typed_fields_no_view_only() -> None:
    """ADR-0065 §四: live SSE frame 的 data 不含 view-only;typed fields 完整传递。"""
    stamped = StampedEvent(
        seq=3,
        ts=1.0,
        scope=RunScope(trace_id="t", run_id="r"),
        event=ToolInvoked(
            tool_name="activate_skill",
            arguments_preview='{"skill_id":"officecli"}',
            result_preview='{"text":"# officecli","skill_id":"officecli"}',
            plugin_state={"content": "# officecli", "success": True},
            code="# officecli",
            language="markdown",
            skill_id="officecli",
        ),
    )
    frame = stamped_to_sse_frame(stamped)
    live = json.loads(next(line[6:] for line in frame.splitlines() if line.startswith("data: ")))
    for forbidden in ("arguments_preview", "result_preview", "plugin_state"):
        assert forbidden not in live["data"], f"{forbidden} leaked to SSE"
    assert live["data"]["code"] == "# officecli"
    assert live["data"]["language"] == "markdown"
    assert live["data"]["skill_id"] == "officecli"

