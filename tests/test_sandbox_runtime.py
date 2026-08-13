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
    async def test_harvest_flag_controls_artifact_scanner(self) -> None:
        from lca.layer0_infra.sandbox.onlyboxes_artifacts import ARTIFACT_BEGIN

        tmp = tempfile.TemporaryDirectory()
        store = LocalFileStore(Path(tmp.name))
        sandbox = InlineSandbox()
        try:
            runtime = await bind_sandbox_runtime("run_hv", sandbox, store, ())
            err = await runtime.ensure_ready()
            self.assertIsNone(err)
            await runtime.execute("print(1)", harvest_artifacts=False)
            self.assertNotIn(ARTIFACT_BEGIN, sandbox.session_run_calls[-1][1])
            await runtime.execute("print(2)", harvest_artifacts=True)
            self.assertIn(ARTIFACT_BEGIN, sandbox.session_run_calls[-1][1])
        finally:
            await runtime.destroy()
            tmp.cleanup()

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
            # 2 calls: 1 from _run_inspect_internal pre-check + 1 user code
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
            # 2 calls: 1 from _run_inspect_internal pre-check + 1 user code
            self.assertEqual(len(sandbox.run_calls), 2)
            self.assertEqual(len(sandbox.created_sessions), 0)
        finally:
            tmp.cleanup()


class TestInlineSandboxWriteFiles(unittest.IsolatedAsyncioTestCase):
    """write_files Protocol method — file staging separated from execution."""

    async def test_write_files_bytes_staged_to_vfs(self) -> None:
        sandbox = InlineSandbox()
        result = await sandbox.write_files({"data.csv": b"a,b\n1,2\n"})
        self.assertTrue(result.success)
        self.assertEqual(len(sandbox.write_files_calls), 1)
        self.assertIn("data.csv", sandbox.write_files_calls[0])

    async def test_write_files_with_session(self) -> None:
        sandbox = InlineSandbox()
        info = await sandbox.create_session()
        assert info is not None
        sid = info.session_id
        await sandbox.write_files({"input.txt": b"hello"}, session_id=sid)
        # File should be in session VFS
        self.assertIn("/mnt/data/input.txt", sandbox._sessions[sid])

    async def test_write_files_str_url_not_written(self) -> None:
        """str values are URLs — InlineSandbox skips them (no curl in tests)."""
        sandbox = InlineSandbox()
        result = await sandbox.write_files({"remote.csv": "https://example.com/data.csv"})
        self.assertTrue(result.success)
        self.assertEqual(len(sandbox.write_files_calls), 1)
        # str values are not written to VFS (only bytes are)

    async def test_run_no_longer_accepts_files(self) -> None:
        """run() signature no longer has files parameter."""
        sandbox = InlineSandbox()
        result = await sandbox.run('print("ok")')
        self.assertTrue(result.success)
        self.assertEqual(sandbox.run_calls, ['print("ok")'])


if __name__ == "__main__":
    unittest.main()
