"""ToolInvoked.files is the durable product channel (not result_preview JSON)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.core.decision import Observation
from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolInvoked,
    run_scope,
)
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.layer0_infra.file_store import LocalFileStore
from lca.layer0_infra.observability import ObservabilityHub, bind
from lca.layer0_infra.tools.write_file import build_tools as build_write_file_tools
from lca.layer1_cognitive.body.safe_executor import (
    SimpleSafeExecutor,
    _tool_output_preview,
)
from lca.layer1_cognitive.body.tool_result_preview import tool_files, tool_plugin_state


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

    def test_result_preview_stays_compact_with_large_streams(self) -> None:
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
        preview = _tool_output_preview(obs)
        self.assertLess(len(preview), 2000)
        parsed = json.loads(preview)
        self.assertEqual(parsed["files"][0]["name"], "chart.png")

    async def test_write_file_emits_structured_files_on_tool_invoked(self) -> None:
        collector = _Collector()
        hub = ObservabilityHub([], journal_projectors=[collector])
        tool = build_write_file_tools(store=self.store)[0]
        executor = SimpleSafeExecutor(
            permission_manifest=ToolPermissionManifest(allowed_tools=["writeFile"])
        )
        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r")):
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
        parsed = json.loads(inv.result_preview)
        self.assertEqual(parsed["name"], "report.md")
        self.assertNotIn("previewHtml", parsed)

    async def test_journal_does_not_truncate_files_field(self) -> None:
        """files is non-string → AttributePolicy leaves it intact through record()."""
        collector = _Collector()
        hub = ObservabilityHub([], journal_projectors=[collector])
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
        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r")):
            from lca.layer0_infra.observability import record

            record(
                ToolInvoked(
                    tool_name="sandbox_execute",
                    result_preview='{"stdout": "' + ("x" * 3000),
                    ok=True,
                    files=many,
                )
            )
        invoked = [s.event for s in collector.received if isinstance(s.event, ToolInvoked)]
        self.assertEqual(len(invoked), 1)
        self.assertEqual(len(invoked[0].files), 8)
        self.assertEqual(invoked[0].files[7]["name"], "chart_7.png")
        # preview still truncated as a string
        self.assertLessEqual(len(invoked[0].result_preview), 2010)

    def test_tool_plugin_state_extracts_structured_state(self) -> None:
        obs = Observation(
            observation_id="obs_1",
            success=True,
            payload={
                "text": "summary for llm",
                "state": {
                    "query": "today news",
                    "resultNumbers": 2,
                    "results": [
                        {"title": "A", "url": "https://a.example", "content": "x" * 500},
                        {"title": "B", "url": "https://b.example", "content": "y" * 500},
                    ],
                    "success": True,
                },
            },
        )
        state = tool_plugin_state(obs)
        self.assertEqual(state["resultNumbers"], 2)
        self.assertEqual(len(state["results"]), 2)
        preview = _tool_output_preview(obs)
        self.assertLess(len(preview), 2000)
        parsed = json.loads(preview)
        self.assertNotIn("state", parsed)

    async def test_journal_preserves_plugin_state_through_policy(self) -> None:
        collector = _Collector()
        hub = ObservabilityHub([], journal_projectors=[collector])
        plugin_state = {
            "query": "news",
            "resultNumbers": 3,
            "results": [
                {"title": f"Hit {i}", "url": f"https://ex/{i}", "content": "z" * 400}
                for i in range(3)
            ],
            "success": True,
        }
        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r")):
            from lca.layer0_infra.observability import record

            record(
                ToolInvoked(
                    tool_name="web_search",
                    result_preview='{"text": "' + ("t" * 3000) + '"}',
                    ok=True,
                    plugin_state=plugin_state,
                )
            )
        invoked = [s.event for s in collector.received if isinstance(s.event, ToolInvoked)]
        self.assertEqual(len(invoked), 1)
        self.assertEqual(len(invoked[0].plugin_state["results"]), 3)
        self.assertEqual(invoked[0].plugin_state["results"][2]["url"], "https://ex/2")


if __name__ == "__main__":
    unittest.main()
