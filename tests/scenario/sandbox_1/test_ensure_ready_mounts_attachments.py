"""Regression: run attachments must be readable at their guest path.

``ensure_ready`` resolves attachments from the ids bound at
``bind_sandbox_runtime`` and stages them under the session root
(todo-79 (b), 6d8ba982e): ``_stage_files`` passes the session id so the
agent's files land in its own session tree. The advertised guest path stays
``/mnt/data/<name>`` (virtual); the adapter rewrites it onto the session
root on backends that map the guest root onto a real host directory.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.sandbox.runtime.scope import bind_sandbox_runtime
from lca.infrastructure.tools.run.finalizer import run_id_scope
from tests.support.inline_sandbox import InlineSandbox

_XLSX = "错误码分类.xlsx"


class TestEnsureReadyStagesAttachments(unittest.IsolatedAsyncioTestCase):
    async def test_bound_attachment_ids_are_mounted_without_ambient_scope(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = LocalFileStore(Path(tmp.name))
        sandbox = InlineSandbox()
        try:
            stored = store.put(
                data=b"xlsx-bytes",
                name=_XLSX,
                mime_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            )
            runtime = await bind_sandbox_runtime(
                "run_mount_regression", sandbox, store, (stored.attachment_id,)
            )
            # No ``run_attachment_scope`` here: ids bound at bind time must be
            # sufficient, so mounting does not depend on ambient contextvars.
            with run_id_scope("run_mount_regression"):
                err = await runtime.ensure_ready()
            self.assertIsNone(err)

            entries = list(runtime.manifest.entries)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].name, _XLSX)
            self.assertEqual(entries[0].path, f"/mnt/data/{_XLSX}")
            self.assertEqual(entries[0].attachment_id, stored.attachment_id)

            # Staged under the session root (todo-79 (b)): _stage_files
            # passes the session id created during ensure_ready, never "".
            stage_calls = [c for c in sandbox.write_files_calls if _XLSX in c[0]]
            self.assertEqual(len(stage_calls), 1)
            self.assertEqual(stage_calls[0][1], sandbox.created_sessions[-1])
            self.assertTrue(stage_calls[0][1], "session_id must not be empty")
            self.assertEqual(stage_calls[0][0][_XLSX], b"xlsx-bytes")
        finally:
            tmp.cleanup()

    async def test_user_code_reads_attachment_at_guest_path(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = LocalFileStore(Path(tmp.name))
        sandbox = InlineSandbox()
        try:
            stored = store.put(data=b"payload-1234", name="input.bin", mime_type="text/plain")
            runtime = await bind_sandbox_runtime(
                "run_mount_read", sandbox, store, (stored.attachment_id,)
            )
            with run_id_scope("run_mount_read"):
                err = await runtime.ensure_ready()
                self.assertIsNone(err)
                result = await runtime.execute(
                    'print(open("/mnt/data/input.bin", "rb").read().decode())'
                )
            self.assertTrue(result.success, result.error)
            self.assertIn("payload-1234", result.stdout)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
