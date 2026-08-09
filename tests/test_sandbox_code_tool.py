"""SandboxCodeTool + SafeExecutor link (inline fake Sandbox — no Mock adapter)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from lca.contracts.models.core.sandbox import (
    SANDBOX_MOUNT_ROOT,
    SANDBOX_OUTPUT_SUBDIR,
    SandboxFile,
    SandboxResult,
)
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
from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter
from lca.layer0_infra.tools.default_set import build_default_tools
from lca.layer0_infra.tools.run_attachment_scope import run_attachment_scope
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


class _InlineSandbox:
    """Test-only Sandbox: exec user code with virtual mounts/outputs."""

    async def run(
        self,
        code: str,
        language: str = "python",
        files: dict[str, bytes] | None = None,
        timeout_s: int = 60,
        **kwargs: Any,
    ) -> SandboxResult:
        del language, timeout_s
        invocation_id = str(kwargs.get("invocation_id", "") or "")
        emitter = SandboxStreamEmitter(invocation_id)
        mounts = dict(files or {})
        outputs: dict[str, bytes] = {}
        out_prefix = f"{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}/"

        def _open(path: str, mode: str = "r", *args: Any, **kw: Any):  # type: ignore[no-untyped-def]
            del args, kw
            path_s = str(path)
            if "b" in mode and "r" in mode and path_s.startswith(f"{SANDBOX_MOUNT_ROOT}/"):
                name = path_s[len(SANDBOX_MOUNT_ROOT) + 1 :]
                if name.startswith(f"{SANDBOX_OUTPUT_SUBDIR}/"):
                    data = outputs.get(path_s, b"")
                else:
                    data = mounts.get(name, b"")
                import io

                return io.BytesIO(data)
            if "w" in mode and path_s.startswith(out_prefix):
                import io

                buf = io.BytesIO()

                class _W:
                    def write(self, data: bytes) -> int:
                        buf.write(data)
                        outputs[path_s] = buf.getvalue()
                        return len(data)

                    def __enter__(self) -> _W:
                        return self

                    def __exit__(self, *a: object) -> None:
                        outputs[path_s] = buf.getvalue()

                return _W()
            raise FileNotFoundError(path_s)

        g: dict[str, Any] = {
            "open": _open,
            "print": print,
            "mounted_files": mounts,
        }

        def save_file(name: str, data: bytes, mime: str = "application/octet-stream") -> None:
            del mime
            outputs[f"{out_prefix}{name}"] = data

        g["save_file"] = save_file

        import contextlib
        import io

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                exec(compile(code, "<inline>", "exec"), g, g)  # noqa: S102
            stdout = buf.getvalue()
            if stdout:
                emitter.emit_stdout(stdout)
            generated = [
                SandboxFile(
                    name=path.rsplit("/", 1)[-1],
                    mime_type="application/octet-stream",
                    data=data,
                )
                for path, data in outputs.items()
            ]
            return SandboxResult(
                stdout=stdout,
                success=True,
                exit_code=0,
                generated_files=tuple(generated),
            )
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"
            emitter.emit_stderr(err + "\n")
            return SandboxResult(success=False, exit_code=1, error=err, stderr=err + "\n")


class SandboxCodeToolTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.store = LocalFileStore(Path(self._tmp.name))
        self.sandbox = _InlineSandbox()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    async def test_inline_run_streams_and_returns_stdout(self) -> None:
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
        self.assertGreaterEqual(len(deltas), 1)
        self.assertEqual(deltas[0].invocation_id, "sbx_test")

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

    async def test_sandbox_tool_auto_mounts_run_attachment_scope(self) -> None:
        """Run-level ambient ids mount without tool-arg attachment_ids (ADR-0046)."""
        stored = self.store.put(
            data=b"xlsx-bytes",
            name="周报-20260116.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        tool = SandboxCodeTool(sandbox=self.sandbox, store=self.store)
        with run_attachment_scope([stored.attachment_id]):
            obs = await tool.execute(
                {
                    "code": (
                        "print(list(mounted_files.keys()))\n"
                        'print(mounted_files["周报-20260116.xlsx"])'
                    ),
                }
            )
        self.assertTrue(obs.success, getattr(obs, "error", None))
        assert isinstance(obs.payload, dict)
        self.assertIn("周报-20260116.xlsx", obs.payload["stdout"])
        self.assertIn("xlsx-bytes", obs.payload["stdout"])

    async def test_sandbox_tool_merges_ambient_and_explicit_attachments(self) -> None:
        a = self.store.put(data=b"aaa", name="a.txt", mime_type="text/plain")
        b = self.store.put(data=b"bbb", name="b.txt", mime_type="text/plain")
        tool = SandboxCodeTool(sandbox=self.sandbox, store=self.store)
        with run_attachment_scope([a.attachment_id]):
            obs = await tool.execute(
                {
                    "code": "print(sorted(mounted_files.keys()))",
                    "attachment_ids": [b.attachment_id],
                }
            )
        self.assertTrue(obs.success)
        assert isinstance(obs.payload, dict)
        self.assertIn("a.txt", obs.payload["stdout"])
        self.assertIn("b.txt", obs.payload["stdout"])

    async def test_safe_executor_propagates_invocation_id(self) -> None:
        from lca.contracts.models.observability.journal import ToolStarted

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
        started = [s.event for s in collector.received if isinstance(s.event, ToolStarted)]
        self.assertEqual(len(started), 1)
        self.assertTrue(started[0].invocation_id.startswith("inv_"))
        invoked = [s.event for s in collector.received if isinstance(s.event, ToolInvoked)]
        self.assertEqual(len(invoked), 1)
        self.assertEqual(invoked[0].invocation_id, started[0].invocation_id)
        self.assertEqual(invoked[0].tool_name, SANDBOX_TOOL_NAME)
        deltas = [s.event for s in collector.received if isinstance(s.event, SandboxOutputDelta)]
        self.assertGreaterEqual(len(deltas), 1)
        self.assertEqual(deltas[0].invocation_id, started[0].invocation_id)

    def test_build_default_tools_omits_sandbox_without_credentials(self) -> None:
        with (
            patch.dict(
                os.environ,
                {
                    "ONLYBOXES_BASE_URL": "",
                    "ONLYBOXES_ACCESS_TOKEN": "",
                },
                clear=False,
            ),
            patch(
                "lca.layer0_infra.sandbox.factory.load_dotenv_if_present",
                lambda: None,
            ),
            patch(
                "lca.layer0_infra.sandbox.factory.onlyboxes_base_url",
                return_value=None,
            ),
            patch(
                "lca.layer0_infra.sandbox.factory.onlyboxes_access_token",
                return_value=None,
            ),
        ):
            tools = build_default_tools(self.store)
        names = {t.name for t in tools}
        self.assertNotIn(SANDBOX_TOOL_NAME, names)
        self.assertNotIn("calculator", names)
        self.assertIn("write_file", names)

    async def test_open_path_roundtrip_to_outputs(self) -> None:
        code = (
            f'data = open("{SANDBOX_MOUNT_ROOT}/input.csv", "rb").read()\n'
            f'open("{SANDBOX_MOUNT_ROOT}/{SANDBOX_OUTPUT_SUBDIR}/echo.csv", "wb").write(data)\n'
        )
        result = await self.sandbox.run(
            code,
            files={"input.csv": b"a,b\n1,2\n"},
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.generated_files), 1)
        self.assertEqual(result.generated_files[0].name, "echo.csv")
        self.assertEqual(result.generated_files[0].data, b"a,b\n1,2\n")


if __name__ == "__main__":
    unittest.main()
