"""Mount verify reads a JSON control document, not mixed stdout.

run_e5077cf26ecd failed executeCode with 预期挂载缺失: ['<parse error>']
because leftover outputs/ PDF bytes were printed onto the same stdout as
the verify JSON, and the parser took the last line.
"""

from __future__ import annotations

import json
import unittest

from lca.contracts.models.core.execution.sandbox import (
    MountEntry,
    MountManifest,
    SandboxErrorKind,
    SandboxResult,
)
from lca.infrastructure.sandbox.onlyboxes.artifacts import ARTIFACT_BEGIN
from lca.infrastructure.sandbox.runtime.mount import (
    parse_mount_verify_stdout,
    verify_mount_or_error,
)


def _ok_json() -> str:
    return json.dumps({"found": {"a.xlsx": 12}, "missing": []}, ensure_ascii=False)


class TestParseMountVerifyStdout(unittest.TestCase):
    def test_plain_json(self) -> None:
        self.assertEqual(parse_mount_verify_stdout(_ok_json()), [])

    def test_json_then_truncated_artifact_block(self) -> None:
        polluted = (
            _ok_json()
            + "\n"
            + ARTIFACT_BEGIN
            + json.dumps([{"name": "old.pdf", "b64": "A" * 8000}])
        )
        self.assertEqual(parse_mount_verify_stdout(polluted), [])

    def test_reports_missing_names(self) -> None:
        raw = json.dumps({"found": {}, "missing": ["a.xlsx"]})
        self.assertEqual(parse_mount_verify_stdout(raw), ["a.xlsx"])

    def test_garbage_is_parse_error(self) -> None:
        self.assertEqual(parse_mount_verify_stdout("not-json\nstill-not"), ["<parse error>"])


class TestVerifyMountOrError(unittest.IsolatedAsyncioTestCase):
    async def test_polluted_stdout_does_not_fail_when_json_is_present(self) -> None:
        stdout = (
            _ok_json()
            + "\n"
            + ARTIFACT_BEGIN
            + json.dumps([{"name": "old.pdf", "b64": "JVBERi0x" + "A" * 200}])
        )
        seen: list[str] = []

        async def execute(code: str, timeout_s: int = 0) -> SandboxResult:
            del timeout_s
            seen.append(code)
            return SandboxResult(success=True, stdout=stdout, exit_code=0)

        manifest = MountManifest(
            entries=(
                MountEntry(
                    path="/mnt/data/a.xlsx",
                    name="a.xlsx",
                    size_bytes=12,
                    attachment_id="att_1",
                ),
            )
        )
        err = await verify_mount_or_error(execute, manifest=manifest, timeout_s=5)
        self.assertIsNone(err)
        self.assertEqual(len(seen), 1)

    async def test_missing_attachment_still_fails(self) -> None:
        async def execute(code: str, timeout_s: int = 0) -> SandboxResult:
            del code, timeout_s
            return SandboxResult(
                success=True,
                stdout=json.dumps({"found": {}, "missing": ["a.xlsx"]}),
                exit_code=0,
            )

        manifest = MountManifest(
            entries=(
                MountEntry(
                    path="/mnt/data/a.xlsx",
                    name="a.xlsx",
                    size_bytes=12,
                    attachment_id="att_1",
                ),
            )
        )
        err = await verify_mount_or_error(execute, manifest=manifest, timeout_s=5)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertFalse(err.success)
        self.assertEqual(err.error_kind, SandboxErrorKind.MOUNT)
        self.assertIn("a.xlsx", err.error_summary)
