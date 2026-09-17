"""Inspect is observation: Excel datetime must serialize; failure must not block ready."""

from __future__ import annotations

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from lca.contracts.models.core.execution.sandbox import (
    SANDBOX_MOUNT_ROOT,
    SANDBOX_OUTPUT_SUBDIR,
    SandboxErrorKind,
    SandboxExecResult,
)
from lca.infrastructure.file.store import LocalFileStore
from lca.infrastructure.sandbox.inspect.prelude import (
    INSPECT_JSONABLE_SRC,
    INSPECT_SCRIPT,
)
from lca.infrastructure.sandbox.runtime.scope import bind_sandbox_runtime
from tests.support.inline_sandbox import InlineSandbox


class TestInspectJsonable(unittest.TestCase):
    def test_datetime_sample_dumps(self) -> None:
        ns: dict[str, object] = {}
        exec(INSPECT_JSONABLE_SRC, ns)  # noqa: S102
        payload = {
            "when": datetime.datetime(2026, 9, 2, 8, 0, 0),
            "day": datetime.date(2026, 9, 9),
        }
        raw = json.dumps(payload, ensure_ascii=False, default=ns["_jsonable"])
        loaded = json.loads(raw)
        self.assertTrue(str(loaded["when"]).startswith("2026-09-02"))
        self.assertEqual(loaded["day"], "2026-09-09")

    def test_guest_script_uses_jsonable_default(self) -> None:
        self.assertIn("default=_jsonable", INSPECT_SCRIPT)
        self.assertIn("def _jsonable", INSPECT_SCRIPT)


class TestInspectDoesNotBlockReady(unittest.IsolatedAsyncioTestCase):
    async def test_failed_inspect_still_marks_ready(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        store = LocalFileStore(Path(tmp.name))
        sandbox = InlineSandbox()
        try:
            runtime = await bind_sandbox_runtime("run_insp", sandbox, store, ())

            async def boom(*, force: bool = False) -> SandboxExecResult:
                del force
                return SandboxExecResult(
                    success=False,
                    error="inspect 执行失败",
                    error_summary="inspect 执行失败",
                    error_kind=SandboxErrorKind.INFRA,
                )

            runtime._run_inspect_internal = boom  # type: ignore[method-assign]
            err = await runtime.ensure_ready()
            self.assertIsNone(err)
            self.assertTrue(runtime.environment_ready)
            result = await runtime.execute('print("ok")', harvest_artifacts=False)
            self.assertTrue(result.success)
            self.assertEqual(result.stdout.strip(), "ok")
            sid = runtime._session.session_id if runtime._session else ""
            await sandbox.write_files(
                {"report.pdf": b"%PDF-1.4 x"},
                base_dir=f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}",
                session_id=sid,
            )
            harvested = await runtime.harvest_output_delta()
            self.assertIn("report.pdf", [f.name for f in harvested])
        finally:
            await runtime.destroy()
            tmp.cleanup()
