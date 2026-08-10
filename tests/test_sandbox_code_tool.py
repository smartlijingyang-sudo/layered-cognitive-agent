"""Sandbox runtime tools + SandboxCodeTool alias (ADR-0050)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lca.contracts.models.core.sandbox import (
    SANDBOX_MOUNT_ROOT,
    SANDBOX_OUTPUT_SUBDIR,
)
from lca.contracts.models.observability.journal import (
    RunScope,
    StampedEvent,
    ToolInvoked,
    ToolStarted,
    run_scope,
)
from lca.contracts.models.team.role_team import CacheConfig, RetryPolicy, ToolPermissionManifest
from lca.layer0_infra.file_store import LocalFileStore
from lca.layer0_infra.observability import ObservabilityHub, bind
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime, unbind_sandbox_runtime
from lca.layer0_infra.tools.default_set import build_default_tools
from lca.layer0_infra.tools.run_attachment_scope import run_attachment_scope
from lca.layer0_infra.tools.run_finalizer import finalize_run, run_id_scope
from lca.layer0_infra.tools.sandbox_code_tool import SANDBOX_TOOL_NAME, SandboxCodeTool
from lca.layer0_infra.tools.sandbox_runtime_tools import (
    SANDBOX_EXECUTE_TOOL_NAME,
    SANDBOX_INSPECT_TOOL_NAME,
    SandboxExecuteTool,
    SandboxInspectTool,
)
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from tests.support.inline_sandbox import InlineSandbox


class _Collector:
    def __init__(self) -> None:
        self.received: list[StampedEvent] = []

    def on_event(self, stamped: StampedEvent) -> None:
        self.received.append(stamped)

    def flush(self) -> None:
        return

    def close(self) -> None:
        return


class SandboxRuntimeToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileStore(Path(self._tmp.name))
        self.sandbox = InlineSandbox()
        self._run_counter = 0
        self._run_ids: list[str] = []

    async def asyncTearDown(self) -> None:
        for rid in self._run_ids:
            await unbind_sandbox_runtime(rid)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _next_run_id(self) -> str:
        self._run_counter += 1
        return f"run_test_{self._run_counter}"

    async def _bind(self, run_id: str | None = None, attachment_ids: tuple[str, ...] = ()) -> str:
        rid = run_id or self._next_run_id()
        with run_attachment_scope(list(attachment_ids)):
            await bind_sandbox_runtime(rid, self.sandbox, self.store, attachment_ids)
        self._run_ids.append(rid)
        return rid

    async def test_execute_lists_mounted_file_via_mnt_data(self) -> None:
        stored = self.store.put(
            data=b"payload-bytes", name="input.bin", mime_type="application/octet-stream"
        )
        rid = await self._bind(attachment_ids=(stored.attachment_id,))
        tool = SandboxExecuteTool(sandbox=self.sandbox, store=self.store)
        with run_id_scope(rid), run_attachment_scope([stored.attachment_id]):
            obs = await tool.execute(
                {
                    "code": (
                        f"import os\n"
                        f'p="{SANDBOX_MOUNT_ROOT}/input.bin"\n'
                        f"print(os.path.getsize(p))\n"
                        f'print(open(p,"rb").read())'
                    ),
                }
            )
        self.assertTrue(obs.success, obs.error)
        assert isinstance(obs.payload, dict)
        self.assertIn("payload-bytes", obs.payload["stdout"])
        self.assertTrue(obs.payload.get("environment_ready"))

    async def test_inspect_returns_profile(self) -> None:
        stored = self.store.put(
            data=b"not-real-xlsx",
            name="sample.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        rid = await self._bind(attachment_ids=(stored.attachment_id,))
        tool = SandboxInspectTool(sandbox=self.sandbox, store=self.store)
        with run_id_scope(rid), run_attachment_scope([stored.attachment_id]):
            obs = await tool.execute({})
        self.assertTrue(obs.success, obs.error)
        assert isinstance(obs.payload, dict)
        self.assertIn("inspect_profile", obs.payload)
        profile = obs.payload["inspect_profile"]
        assert isinstance(profile, dict)
        self.assertGreaterEqual(len(profile.get("files", [])), 1)

    async def test_sandbox_code_tool_alias(self) -> None:
        rid = await self._bind()
        tool = SandboxCodeTool(sandbox=self.sandbox, store=self.store)
        with run_id_scope(rid):
            obs = await tool.execute({"code": 'print("alias-ok")'})
        self.assertTrue(obs.success)
        assert isinstance(obs.payload, dict)
        self.assertIn("alias-ok", obs.payload["stdout"])

    async def test_auto_mounts_run_attachment_scope(self) -> None:
        stored = self.store.put(
            data=b"xlsx-bytes",
            name="周报-20260116.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        rid = await self._bind(attachment_ids=(stored.attachment_id,))
        tool = SandboxExecuteTool(sandbox=self.sandbox, store=self.store)
        with run_id_scope(rid), run_attachment_scope([stored.attachment_id]):
            obs = await tool.execute(
                {
                    "code": (
                        f"import os\n"
                        f'print(os.path.getsize("{SANDBOX_MOUNT_ROOT}/周报-20260116.xlsx"))'
                    ),
                }
            )
        self.assertTrue(obs.success, getattr(obs, "error", None))
        assert isinstance(obs.payload, dict)
        manifest = obs.payload.get("mount_manifest")
        assert isinstance(manifest, list)
        names = {entry.get("name") for entry in manifest if isinstance(entry, dict)}
        self.assertIn("周报-20260116.xlsx", names)

    async def test_session_reused_across_calls(self) -> None:
        rid = await self._bind()
        tool = SandboxExecuteTool(sandbox=self.sandbox, store=self.store)
        with run_id_scope(rid):
            await tool.execute({"code": 'print("one")'})
            await tool.execute({"code": 'print("two")'})
        self.assertEqual(len(self.sandbox.created_sessions), 1)
        # 3 calls: 1 inspect (ensure_ready) + 2 user code
        self.assertEqual(len(self.sandbox.session_run_calls), 3)
        await unbind_sandbox_runtime(rid)
        self.assertEqual(self.sandbox.destroyed_sessions, ["sess_1"])

    async def test_safe_executor_propagates_invocation_id(self) -> None:
        rid = await self._bind()
        tool = SandboxCodeTool(sandbox=self.sandbox, store=self.store)
        collector = _Collector()
        hub = ObservabilityHub([], journal_projectors=[collector])
        executor = SimpleSafeExecutor(
            ToolPermissionManifest(allowed_tools=[SANDBOX_TOOL_NAME, SANDBOX_EXECUTE_TOOL_NAME])
        )
        with bind(hub), run_scope(RunScope(trace_id="t", run_id=rid)), run_id_scope(rid):
            obs = await executor.execute(
                tool,
                {"code": 'print("x")'},
                RetryPolicy(max_retries=0),
                CacheConfig(enabled=False),
            )
        self.assertTrue(obs.success)
        started = [s.event for s in collector.received if isinstance(s.event, ToolStarted)]
        self.assertEqual(len(started), 1)
        invoked = [s.event for s in collector.received if isinstance(s.event, ToolInvoked)]
        self.assertEqual(invoked[0].invocation_id, started[0].invocation_id)

    async def test_structured_error_on_user_code_failure(self) -> None:
        rid = await self._bind()
        tool = SandboxExecuteTool(sandbox=self.sandbox, store=self.store)
        with run_id_scope(rid):
            obs = await tool.execute({"code": "raise ValueError('bad input')"})
        self.assertFalse(obs.success)
        assert isinstance(obs.payload, dict)
        self.assertEqual(obs.payload.get("error_kind"), "user_code")

    def test_build_default_tools_excludes_raw_sandbox_tools(self) -> None:
        with (
            patch.dict(
                os.environ, {"ONLYBOXES_BASE_URL": "http://x", "ONLYBOXES_ACCESS_TOKEN": "obx_x"}
            ),
            patch("lca.layer0_infra.sandbox.factory.onlyboxes_base_url", return_value="http://x"),
            patch("lca.layer0_infra.sandbox.factory.onlyboxes_access_token", return_value="obx_x"),
        ):
            tools = build_default_tools(self.store)
        names = {t.name for t in tools}
        self.assertNotIn(SANDBOX_INSPECT_TOOL_NAME, names)
        self.assertNotIn(SANDBOX_EXECUTE_TOOL_NAME, names)
        self.assertNotIn(SANDBOX_TOOL_NAME, names)
        self.assertIn("run_skill_script", names)

    async def test_open_path_roundtrip_to_outputs(self) -> None:
        code = (
            f'data = open("{SANDBOX_MOUNT_ROOT}/input.csv", "rb").read()\n'
            f'open("{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}/echo.csv", "wb").write(data)\n'
        )
        await self.sandbox.write_files({"input.csv": b"a,b\n1,2\n"})
        result = await self.sandbox.run(code)
        self.assertTrue(result.success)
        self.assertEqual(len(result.generated_files), 1)
        self.assertEqual(result.generated_files[0].name, "echo.csv")

    async def test_finalize_run_destroys_runtime(self) -> None:
        rid = await self._bind(run_id="run_fin")
        with run_id_scope(rid):
            tool = SandboxExecuteTool(sandbox=self.sandbox, store=self.store)
            await tool.execute({"code": 'print("z")'})
        await finalize_run(rid)
        self.assertEqual(self.sandbox.destroyed_sessions, ["sess_1"])


if __name__ == "__main__":
    unittest.main()
