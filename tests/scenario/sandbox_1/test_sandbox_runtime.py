"""Run-bound sandbox runtime lifecycle (ADR-0050)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.core.execution.sandbox import (
    SANDBOX_MOUNT_ROOT,
    SANDBOX_OUTPUT_SUBDIR,
)
from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.sandbox.onlyboxes.artifacts import ARTIFACT_BEGIN
from lca.infrastructure.sandbox.runtime.scope import bind_sandbox_runtime, get_sandbox_runtime
from lca.infrastructure.tools.run.finalizer import finalize_run, run_id_scope
from lca.infrastructure.tools.sandbox.runtime_tools import SandboxExecuteTool
from tests.support.inline_sandbox import InlineSandbox


class TestSandboxRuntimeLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_harvest_flag_controls_artifact_scanner(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = LocalFileStore(Path(tmp.name))
        sandbox = InlineSandbox()
        try:
            runtime = await bind_sandbox_runtime("run_hv", sandbox, store, ())
            err = await runtime.ensure_ready()
            self.assertIsNone(err)
            await runtime.execute("print(1)", harvest_artifacts=False)
            user_off = sandbox.session_run_calls[-1][1]
            self.assertIn("print(1)", user_off)
            self.assertNotIn(ARTIFACT_BEGIN, user_off)
            await runtime.execute("print(2)", harvest_artifacts=True)
            harvest = sandbox.session_run_calls[-1][1]
            user_on = sandbox.session_run_calls[-2][1]
            self.assertIn("print(2)", user_on)
            self.assertNotIn(ARTIFACT_BEGIN, user_on)
            self.assertIn(ARTIFACT_BEGIN, harvest)
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
            codes = [c[1] for c in sandbox.session_run_calls]
            self.assertTrue(any('print("hello")' in c and ARTIFACT_BEGIN not in c for c in codes))
            self.assertTrue(any(ARTIFACT_BEGIN in c for c in codes))

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
            self.assertTrue(
                any(
                    'print("stateless")' in c and ARTIFACT_BEGIN not in c for c in sandbox.run_calls
                )
            )
            self.assertTrue(any(ARTIFACT_BEGIN in c for c in sandbox.run_calls))
            self.assertEqual(len(sandbox.created_sessions), 0)
        finally:
            tmp.cleanup()


class TestOutputChannelSplit(unittest.IsolatedAsyncioTestCase):
    async def test_preexisting_output_is_not_republished(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = LocalFileStore(Path(tmp.name))
        sandbox = InlineSandbox()
        try:
            await sandbox.write_files(
                {"old.pdf": b"%PDF-1.4 leftover"},
                base_dir=f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}",
            )
            runtime = await bind_sandbox_runtime("run_base", sandbox, store, ())
            err = await runtime.ensure_ready()
            self.assertIsNone(err)
            result = await runtime.execute('print("ok")')
            self.assertTrue(result.success)
            self.assertEqual(result.stdout.strip(), "ok")
            self.assertNotIn("old.pdf", [f.name for f in result.generated_files])
            written = await runtime.execute(
                'open("/mnt/data/outputs/new.txt", "wb").write(b"hi")\n'
            )
            names = [f.name for f in written.generated_files]
            self.assertIn("new.txt", names)
            self.assertNotIn("old.pdf", names)
        finally:
            await runtime.destroy()
            tmp.cleanup()


class TestInlineSandboxWriteFiles(unittest.IsolatedAsyncioTestCase):
    """write_files Protocol method — file staging separated from execution."""

    async def test_write_files_bytes_staged_to_vfs(self) -> None:
        sandbox = InlineSandbox()
        result = await sandbox.write_files({"data.csv": b"a,b\n1,2\n"})
        self.assertTrue(result.success)
        self.assertEqual(len(sandbox.write_files_calls), 1)
        self.assertIn("data.csv", sandbox.write_files_calls[0][0])

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
