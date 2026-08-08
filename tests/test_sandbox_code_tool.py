"""ADR-0044: Mock sandbox + SandboxCodeTool + journal stream + SafeExecutor link."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.observability.journal import (
    RunScope,
    SandboxOutputDelta,
    StampedEvent,
    ToolInvoked,
    run_scope,
)
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.layer0_infra.file_store import LocalFileStore
from lca.layer0_infra.observability import ObservabilityHub, bind
from lca.layer0_infra.sandbox.mock_adapter import MockSandboxAdapter
from lca.layer0_infra.tools.default_set import build_default_tools
from lca.layer0_infra.tools.sandbox_code_tool import SANDBOX_TOOL_NAME, SandboxCodeTool
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor


class _Collector:
    def __init__(self) -> None:
        self.received: list[StampedEvent] = []

    def on_event(self, stamped: StampedEvent) -> None:
        self.received.append(stamped)

    def flush(self) -> None:
        return

    def close(self) -> None:
        return


class MockSandboxAndToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileStore(Path(self._tmp.name))
        self.sandbox = MockSandboxAdapter()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_mock_run_streams_and_returns_stdout(self) -> None:
        collector = _Collector()
        hub = ObservabilityHub([], journal_projectors=[collector])
        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r", agent_role="dev")):
            result = await self.sandbox.run(
                'print("hi")\nprint("there")',
                invocation_id="sbx_test",
            )
        self.assertTrue(result.success)
        self.assertIn("hi", result.stdout)
        deltas = [s.event for s in collector.received if isinstance(s.event, SandboxOutputDelta)]
        self.assertGreaterEqual(len(deltas), 2)
        self.assertEqual(deltas[0].invocation_id, "sbx_test")
        self.assertEqual(deltas[0].stream, "stdout")
        self.assertEqual(deltas[0].seq, 0)
        self.assertEqual(deltas[1].seq, 1)

    async def test_sandbox_tool_multi_file_payload_and_invocation_id(self) -> None:
        tool = SandboxCodeTool(sandbox=self.sandbox, store=self.store)
        code = (
            'print("ok")\n'
            'save_file("out.csv", b"a,b\\n1,2\\n", "text/csv")\n'
            'save_file("note.txt", b"hello", "text/plain")\n'
        )
        obs = await tool.execute({"code": code})
        self.assertTrue(obs.success)
        assert isinstance(obs.payload, dict)
        self.assertIn("stdout", obs.payload)
        self.assertIn("files", obs.payload)
        self.assertEqual(len(obs.payload["files"]), 2)
        self.assertTrue(str(obs.extra.get("invocation_id", "")).startswith("sbx_"))
        for part in obs.payload["files"]:
            self.assertIn("mimeType", part)
            self.assertIn("attachmentId", part)
            self.assertTrue(self.store.exists(part["attachmentId"]))

    async def test_sandbox_tool_mounts_attachments(self) -> None:
        stored = self.store.put(
            data=b"payload-bytes",
            name="input.bin",
            mime_type="application/octet-stream",
        )
        tool = SandboxCodeTool(sandbox=self.sandbox, store=self.store)
        obs = await tool.execute(
            {
                "code": ('print(list(mounted_files.keys()))\nprint(mounted_files["input.bin"])'),
                "attachment_ids": [stored.attachment_id],
            }
        )
        self.assertTrue(obs.success)
        assert isinstance(obs.payload, dict)
        self.assertIn("input.bin", obs.payload["stdout"])

    async def test_safe_executor_propagates_invocation_id(self) -> None:
        tool = SandboxCodeTool(sandbox=self.sandbox, store=self.store)
        collector = _Collector()
        hub = ObservabilityHub([], journal_projectors=[collector])
        executor = SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[SANDBOX_TOOL_NAME]))
        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r")):
            obs = await executor.execute(
                tool,
                {"code": 'print("x")'},
                RetryPolicy(max_retries=0),
                CacheConfig(enabled=False),
            )
        self.assertTrue(obs.success)
        invoked = [s.event for s in collector.received if isinstance(s.event, ToolInvoked)]
        self.assertEqual(len(invoked), 1)
        self.assertTrue(invoked[0].invocation_id.startswith("sbx_"))
        self.assertEqual(invoked[0].tool_name, SANDBOX_TOOL_NAME)
        deltas = [s.event for s in collector.received if isinstance(s.event, SandboxOutputDelta)]
        self.assertGreaterEqual(len(deltas), 1)

    def test_build_default_tools_omits_sandbox_without_key(self) -> None:
        tools = build_default_tools(self.store, include_sandbox_mock=False)
        names = {t.name for t in tools}
        self.assertNotIn(SANDBOX_TOOL_NAME, names)
        tools_mock = build_default_tools(self.store, include_sandbox_mock=True)
        self.assertIn(SANDBOX_TOOL_NAME, {t.name for t in tools_mock})


if __name__ == "__main__":
    unittest.main()
