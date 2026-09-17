"""Regression: harvested sandbox files must reach ``ToolResult.files_created``.

``_extract_files_created`` read ``extra["files_created"]``, a key nothing in
``lca/`` ever writes. The sandbox harvest stores A2A file metadata dicts under
``payload["files"]`` and ``extra["files"]``
(``infrastructure/tools/sandbox/exec_observation.py``), so the extractor always
returned ``()``. In ``run_5490e7c8a76c`` the run wrote four PNG charts and one
HTML report into ``outputs/`` and every journal step recorded
``files_created=[]``, leaving the durable record with no fact naming the
deliverables. The same blindness made ``_delta_summary_from_obs`` skip its
"wrote N files" branch on every step.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from lca.cognition.body.executor.safe_executor import (
    SimpleSafeExecutor,
    _delta_summary_from_obs,
    _extract_files_created,
)
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.team.role.team import (
    CacheConfig,
    RetryPolicy,
    ToolPermissionManifest,
)

_HARVESTED = [
    {
        "name": "chart1_category.png",
        "mimeType": "image/png",
        "sizeBytes": 20481,
        "url": "/files/att_chart1",
        "previewable": True,
        "attachmentId": "att_chart1",
    },
    {
        "name": "项目进度可视化分析报告.html",
        "mimeType": "text/html",
        "sizeBytes": 40122,
        "url": "/files/att_report",
        "previewable": True,
        "attachmentId": "att_report",
    },
]


def _harvest_observation() -> Observation:
    return Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"stdout": "所有图表已生成", "exit_code": 0, "files": _HARVESTED},
        extra={"invocation_id": "toolu_x", "files": _HARVESTED},
    )


def test_extracts_names_from_harvested_extra_files() -> None:
    assert _extract_files_created(_harvest_observation()) == (
        "chart1_category.png",
        "项目进度可视化分析报告.html",
    )


def test_extracts_names_from_payload_when_extra_absent() -> None:
    obs = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"stdout": "ok", "files": _HARVESTED},
        extra={},
    )
    assert _extract_files_created(obs) == (
        "chart1_category.png",
        "项目进度可视化分析报告.html",
    )


def test_plain_string_entries_still_work() -> None:
    obs = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"files_created": ["report.md"]},
    )
    assert _extract_files_created(obs) == ("report.md",)


def test_no_files_returns_empty() -> None:
    obs = Observation(
        observation_id=new_id("obs"), success=True, payload={"stdout": "ok"}, extra={}
    )
    assert _extract_files_created(obs) == ()


def test_delta_summary_reports_written_files() -> None:
    assert _delta_summary_from_obs(_harvest_observation()).startswith("✅ 写出 2 个文件")


@dataclass
class _HarvestTool:
    name: str = "executeCode"

    async def execute(self, args: dict[str, Any]) -> Observation:  # type: ignore[override]
        return _harvest_observation()

    def is_idempotent(self) -> bool:
        return True


def test_tool_result_fact_carries_the_harvested_names() -> None:
    """End to end through the seam that writes the durable fact."""
    captured: list[tuple[str, dict[str, Any]]] = []

    def fake_publish_ep(
        ep: str,
        payload: dict[str, Any],
        *,
        state: Any = None,
        session: Any = None,
        actor: str = "body",
    ) -> None:
        captured.append((ep, dict(payload)))

    executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=["executeCode"]))
    with patch(
        "lca.loop.commit.tool_journal.publish_ep_bound",
        side_effect=fake_publish_ep,
    ):
        asyncio.run(
            executor.execute(
                _HarvestTool(),
                {"code": "print(1)"},
                RetryPolicy(),
                CacheConfig(enabled=False),
                invocation_id="inv-files",
            )
        )

    results = [p for ep, p in captured if ep == "step.tool_result.record"]
    assert len(results) == 1, f"expected one step.tool_result.record, got {results}"
    assert results[0]["files_created"] == [
        "chart1_category.png",
        "项目进度可视化分析报告.html",
    ]
