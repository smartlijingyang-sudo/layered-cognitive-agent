"""run_command / run_terminal auto-harvest of /mnt/data/outputs (ADR-0046)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT, SANDBOX_OUTPUT_SUBDIR
from lca.infrastructure.computer.runtime import ComputerRuntime
from lca.infrastructure.file_store import LocalFileStore
from lca.infrastructure.sandbox.runtime import RunBoundSandboxRuntime
from tests.support.inline_sandbox import InlineSandbox


class TestRunTerminalOutputHarvest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileStore(root=Path(self._tmp.name) / "files")
        self.sandbox = InlineSandbox()
        self.runtime = RunBoundSandboxRuntime(
            sandbox=self.sandbox,
            store=self.store,
            run_id="run_harvest_test",
        )
        err = await self.runtime.ensure_ready()
        self.assertIsNone(err)
        assert self.runtime._session is not None
        self.session_id = self.runtime._session.session_id

    async def asyncTearDown(self) -> None:
        await self.runtime.destroy()
        self._tmp.cleanup()

    async def _stage_output(self, name: str, data: bytes) -> None:
        await self.sandbox.write_files(
            {name: data},
            base_dir=f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}",
            session_id=self.session_id,
        )

    async def test_run_terminal_harvests_new_outputs(self) -> None:
        await self._stage_output("chart.png", b"\x89PNG-v1")
        result = await self.runtime.run_terminal("echo ok", invocation_id="t1")
        names = [f.name for f in result.generated_files]
        self.assertIn("chart.png", names)
        chart = next(f for f in result.generated_files if f.name == "chart.png")
        self.assertEqual(chart.data, b"\x89PNG-v1")

    async def test_unchanged_output_not_reharvested(self) -> None:
        await self._stage_output("chart.png", b"\x89PNG-same")
        first = await self.runtime.run_terminal("echo 1", invocation_id="t1")
        self.assertTrue(any(f.name == "chart.png" for f in first.generated_files))
        second = await self.runtime.run_terminal("echo 2", invocation_id="t2")
        self.assertFalse(any(f.name == "chart.png" for f in second.generated_files))

    async def test_changed_content_is_reharvested(self) -> None:
        await self._stage_output("chart.png", b"\x89PNG-v1")
        await self.runtime.run_terminal("echo 1", invocation_id="t1")
        await self._stage_output("chart.png", b"\x89PNG-v2-changed")
        again = await self.runtime.run_terminal("echo 2", invocation_id="t2")
        chart = next(f for f in again.generated_files if f.name == "chart.png")
        self.assertEqual(chart.data, b"\x89PNG-v2-changed")

    async def test_harvest_outputs_false_skips(self) -> None:
        await self._stage_output("secret.bin", b"no-auto")
        result = await self.runtime.run_terminal(
            "echo skip",
            invocation_id="t1",
            harvest_outputs=False,
        )
        self.assertEqual(result.generated_files, ())

    async def test_execute_fingerprint_suppresses_later_terminal_dup(self) -> None:
        # execute_code path remembers fingerprints
        await self.runtime.execute(
            'open("/mnt/data/outputs/from_py.bin","wb").write(b"x")\n',
            invocation_id="exec1",
        )
        term = await self.runtime.run_terminal("echo after-exec", invocation_id="t1")
        self.assertFalse(any(f.name == "from_py.bin" for f in term.generated_files))


class TestRunCommandSurfacesFiles(unittest.IsolatedAsyncioTestCase):
    async def test_computer_run_command_state_files(self) -> None:
        from lca.infrastructure.sandbox.runtime_scope import (
            bind_sandbox_runtime,
            unbind_sandbox_runtime,
        )
        from lca.infrastructure.tools.run_finalizer import run_id_scope

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalFileStore(root=Path(os.path.join(tmp, "files")))
            sandbox = InlineSandbox()
            rt = ComputerRuntime(sandbox=sandbox, store=store)
            rid = "cmd_files_run"
            runtime = await bind_sandbox_runtime(rid, sandbox, store, ())
            await runtime.ensure_ready()
            assert runtime._session is not None
            try:
                await sandbox.write_files(
                    {"analysis.pptx": b"PK-deck", "chart.png": b"\x89PNG"},
                    base_dir=f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}",
                    session_id=runtime._session.session_id,
                )
                with run_id_scope(rid):
                    mutate = await rt.run_command(command="echo done")
                    close = await rt.run_command(
                        command="officecli close /mnt/data/outputs/analysis.pptx --json"
                    )
            finally:
                await unbind_sandbox_runtime(rid)

            mutate_names = {f["name"] for f in (mutate.state.get("files") or [])}
            self.assertIn("chart.png", mutate_names)
            self.assertNotIn("analysis.pptx", mutate_names)
            close_names = {f["name"] for f in (close.state.get("files") or [])}
            self.assertIn("analysis.pptx", close_names)


if __name__ == "__main__":
    unittest.main()
