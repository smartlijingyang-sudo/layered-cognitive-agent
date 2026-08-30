"""ToolInvoked.files is the durable product channel.

ADR-0101 PR-2:tool 事件 dataclass 不再带 ``result_preview`` /
``plugin_state`` / ``_tool_output_preview``;输出走 ``output_ref``
evidence 平面,文件元数据走 ``files`` typed 字段(永不截断)。
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolInvoked,
)
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.infrastructure.file_store import LocalFileStore
from lca.infrastructure.observability import bind_backends, run_scope
from lca.infrastructure.tools.write_file import build_tools as build_write_file_tools
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.tool_result_preview import tool_files
from tests.support.observability_helpers import make_test_bound


class _Collector:
    def __init__(self) -> None:
        self.received: list[StampedEvent] = []

    def on_event(self, stamped: StampedEvent) -> None:
        self.received.append(stamped)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


class ToolInvokedFilesTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileStore(Path(self._tmp.name))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_tool_files_strips_preview_html(self) -> None:
        obs = Observation(
            observation_id="obs_1",
            success=True,
            payload={
                "name": "a.html",
                "mimeType": "text/html",
                "url": "/files/a",
                "previewHtml": "<html>huge</html>",
            },
            extra={
                "files": [
                    {
                        "name": "a.html",
                        "mimeType": "text/html",
                        "url": "/files/a",
                        "previewHtml": "<html>huge</html>",
                        "attachmentId": "file_a",
                    }
                ]
            },
        )
        files = tool_files(obs)
        self.assertEqual(len(files), 1)
        self.assertNotIn("previewHtml", files[0])
        self.assertEqual(files[0]["name"], "a.html")

    def test_tool_files_handles_large_streams(self) -> None:
        """files 是 typed 字段,AttributePolicy 不截断;大流可携带在
        output_ref 平面。"""
        obs = Observation(
            observation_id="obs_1",
            success=True,
            payload={
                "stdout": "S" * 5000,
                "stderr": "E" * 5000,
                "files": [
                    {
                        "name": "chart.png",
                        "mimeType": "image/png",
                        "url": "/files/c",
                        "previewable": True,
                    }
                ],
                "exit_code": 0,
            },
            extra={
                "files": [
                    {
                        "name": "chart.png",
                        "mimeType": "image/png",
                        "url": "/files/c",
                        "previewable": True,
                    }
                ]
            },
        )
        files = tool_files(obs)
        # files 字段是 metadata-only,不携带 body
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["name"], "chart.png")

    async def test_write_file_emits_structured_files_on_tool_invoked(self) -> None:
        """ADR-0101 PR-2:writeFile 工具 emit ToolInvoked with ``files`` typed
        field;输出数据走 ``output_ref``(evidence 平面),不落 disk 在 ``data``。"""
        collector = _Collector()
        hub = make_test_bound(projections=[collector])
        tool = build_write_file_tools(store=self.store)[0]
        executor = SimpleSafeExecutor(
            permission_manifest=ToolPermissionManifest(allowed_tools=["writeFile"])
        )
        with bind_backends(hub), run_scope(RunScope(trace_id="t", run_id="r")):
            obs = await executor.execute(
                tool,
                {
                    "name": "report.md",
                    "content": "# Title\n\nbody",
                    "mime_type": "text/markdown",
                },
                RetryPolicy(max_retries=0),
                CacheConfig(enabled=False),
            )
        self.assertTrue(obs.success)
        invoked = [s.event for s in collector.received if isinstance(s.event, ToolInvoked)]
        self.assertEqual(len(invoked), 1)
        inv = invoked[0]
        self.assertTrue(inv.ok)
        self.assertGreaterEqual(len(inv.files), 1)
        self.assertEqual(inv.files[0]["name"], "report.md")
        self.assertTrue(inv.files[0].get("previewable"))

    async def test_journal_does_not_truncate_files_field(self) -> None:
        """files 是 typed 字段 → AttributePolicy 保留完整 tuple。"""
        collector = _Collector()
        hub = make_test_bound(projections=[collector])
        many = tuple(
            {
                "name": f"chart_{i}.png",
                "mimeType": "image/png",
                "url": f"/files/f{i}",
                "previewable": True,
                "attachmentId": f"file_{i}",
            }
            for i in range(8)
        )
        with bind_backends(hub), run_scope(RunScope(trace_id="t", run_id="r")):
            from lca.infrastructure.observability import record

            record(
                ToolInvoked(
                    tool_name="sandbox_execute",
                    ok=True,
                    files=many,
                )
            )
        invoked = [s.event for s in collector.received if isinstance(s.event, ToolInvoked)]
        self.assertEqual(len(invoked), 1)
        self.assertEqual(len(invoked[0].files), 8)
        self.assertEqual(invoked[0].files[7]["name"], "chart_7.png")


if __name__ == "__main__":
    unittest.main()
