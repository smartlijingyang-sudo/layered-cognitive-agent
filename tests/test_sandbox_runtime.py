"""Run-bound sandbox runtime lifecycle (ADR-0050)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.layer0_infra.file_store import LocalFileStore
from lca.layer0_infra.sandbox.runtime_scope import bind_sandbox_runtime, get_sandbox_runtime
from lca.layer0_infra.tools.run_finalizer import finalize_run, run_id_scope
from lca.layer0_infra.tools.sandbox_runtime_tools import SandboxExecuteTool
from tests.support.inline_sandbox import InlineSandbox


class TestSandboxRuntimeLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_bind_ensure_execute_finalize(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = LocalFileStore(Path(tmp.name))
        sandbox = InlineSandbox()
        try:
            runtime = await bind_sandbox_runtime("run_lc", sandbox, store, ())
            self.assertIs(get_sandbox_runtime("run_lc"), runtime)
            err = await runtime.ensure_ready()
            self.assertIsNone(err)
            self.assertTrue(runtime.environment_ready)

            tool = SandboxExecuteTool(sandbox=sandbox, store=store)
            with run_id_scope("run_lc"):
                obs = await tool.execute({"code": 'print("hello")'})
            self.assertTrue(obs.success)
            self.assertEqual(len(sandbox.session_run_calls), 2)

            await finalize_run("run_lc")
            self.assertEqual(sandbox.destroyed_sessions, ["sess_1"])
            self.assertIsNone(get_sandbox_runtime("run_lc"))
        finally:
            tmp.cleanup()

    async def test_stateless_fallback_when_no_session(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = LocalFileStore(Path(tmp.name))
        sandbox = InlineSandbox(session_ok=False)
        try:
            runtime = await bind_sandbox_runtime("run_ns", sandbox, store, ())
            err = await runtime.ensure_ready()
            self.assertIsNone(err)
            with run_id_scope("run_ns"):
                tool = SandboxExecuteTool(sandbox=sandbox, store=store)
                obs = await tool.execute({"code": 'print("stateless")'})
            self.assertTrue(obs.success)
            self.assertEqual(len(sandbox.run_calls), 2)
            self.assertEqual(len(sandbox.created_sessions), 0)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
