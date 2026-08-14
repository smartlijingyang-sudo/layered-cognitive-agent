"""Onlyboxes sandbox adapter + factory (HTTP mocked)."""

from __future__ import annotations

import base64
import json
import os
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from lca.layer0_infra.sandbox.factory import resolve_sandbox, sandbox_backend
from lca.layer0_infra.sandbox.onlyboxes_adapter import OnlyboxesSandboxAdapter
from lca.layer0_infra.sandbox.onlyboxes_artifacts import (
    ARTIFACT_BEGIN,
    ARTIFACT_END,
    strip_artifacts,
)
from lca.layer0_infra.sandbox.paths import ONLYBOXES


def _artifact_block(files: list[tuple[str, bytes]]) -> str:
    payload = [
        {"name": name, "b64": base64.b64encode(data).decode("ascii")} for name, data in files
    ]
    return ARTIFACT_BEGIN + json.dumps(payload) + ARTIFACT_END


def _terminal_ok_response() -> MagicMock:
    """Build a mock response matching POST /api/v1/commands/terminal success."""
    resp = MagicMock()
    resp.status_code = 200
    resp.text = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""})
    resp.ok = True
    return resp


# ── bootstrap / artifact unit tests ─────────────────────────────────


class StripArtifactsTests(unittest.TestCase):
    def test_extracts_files_and_cleans_stdout(self) -> None:
        stdout = "hello\n" + _artifact_block([("out.txt", b"abc")]) + "\n"
        cleaned, files, diags = strip_artifacts(stdout)
        self.assertIn("hello", cleaned)
        self.assertNotIn(ARTIFACT_BEGIN, cleaned)
        self.assertEqual(diags, [])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].name, "out.txt")
        self.assertEqual(files[0].data, b"abc")


# ── factory tests ────────────────────────────────────────────────────


class FactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {
            k: os.environ.get(k)
            for k in (
                "ONLYBOXES_BASE_URL",
                "ONLYBOXES_ACCESS_TOKEN",
                "LCA_SANDBOX_BACKEND",
            )
        }

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_missing_credentials_returns_none(self) -> None:
        os.environ.pop("ONLYBOXES_BASE_URL", None)
        os.environ.pop("ONLYBOXES_ACCESS_TOKEN", None)
        os.environ.pop("LCA_SANDBOX_BACKEND", None)
        with patch(
            "lca.layer0_infra.sandbox.factory.load_dotenv_if_present",
            lambda: None,
        ):
            self.assertIsNone(resolve_sandbox())

    def test_credentials_return_onlyboxes_adapter(self) -> None:
        os.environ["ONLYBOXES_BASE_URL"] = "http://127.0.0.1:8089"
        os.environ["ONLYBOXES_ACCESS_TOKEN"] = "obx_test"  # noqa: S105
        os.environ["LCA_SANDBOX_BACKEND"] = "onlyboxes"
        with patch(
            "lca.layer0_infra.sandbox.factory.load_dotenv_if_present",
            lambda: None,
        ):
            sandbox = resolve_sandbox()
        self.assertIsInstance(sandbox, OnlyboxesSandboxAdapter)
        self.assertEqual(sandbox_backend(), "onlyboxes")


# ── adapter tests (unified terminalExec channel) ────────────────────


class OnlyboxesAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_uses_terminal_endpoint(self) -> None:
        """run() should write code to /tmp then execute via terminalExec."""
        response = MagicMock()
        response.status_code = 200
        response.text = json.dumps({"exit_code": 0, "stdout": "42\n", "stderr": ""})
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client.aclose = AsyncMock()

        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="obx_token",  # noqa: S106
            client=client,
        )
        result = await adapter.run("print(42)", invocation_id="sbx_1")

        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "42\n")

        # All calls go through /api/v1/commands/terminal
        for call in client.post.await_args_list:
            self.assertIn("/api/v1/commands/terminal", call.args[0])

        # Last call should be the python3 execution command
        last_body: dict[str, Any] = client.post.await_args_list[-1].kwargs["json"]
        self.assertIn("python3", last_body["command"])
        self.assertIn("/tmp/lca-code-", last_body["command"])  # noqa: S108

    async def test_http_error_surface(self) -> None:
        response = MagicMock()
        response.status_code = 401
        response.text = json.dumps({"error": "invalid or missing token"})
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client.aclose = AsyncMock()
        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="bad",  # noqa: S106
            client=client,
        )
        result = await adapter.run("print(1)")
        self.assertFalse(result.success)
        self.assertIn("token", result.error.lower())

    async def test_run_terminal_delegates_to_exec_terminal(self) -> None:
        """run_terminal() should go through _exec_terminal."""
        response = MagicMock()
        response.status_code = 200
        response.text = json.dumps({"exit_code": 0, "stdout": "ok\n", "stderr": ""})
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client.aclose = AsyncMock()

        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="tok",  # noqa: S106
            client=client,
        )
        result = await adapter.run_terminal("ls -la", invocation_id="term_1")

        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "ok\n")
        call_body: dict[str, Any] = client.post.await_args.kwargs["json"]
        self.assertEqual(call_body["command"], ONLYBOXES.with_cwd("ls -la"))
        self.assertTrue(call_body["create_if_missing"])

    async def test_create_session_returns_session_info(self) -> None:
        """create_session() should issue a no-op command and return SessionInfo."""
        response = MagicMock()
        response.status_code = 200
        response.text = json.dumps({"exit_code": 0, "stdout": "", "stderr": ""})
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client.aclose = AsyncMock()

        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="tok",  # noqa: S106
            client=client,
        )
        session = await adapter.create_session()

        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, "terminal-session")
        call_body: dict[str, Any] = client.post.await_args.kwargs["json"]
        self.assertEqual(call_body["command"], ONLYBOXES.with_cwd(":"))

    async def test_destroy_session_sends_delete(self) -> None:
        client = AsyncMock()
        client.delete = AsyncMock()
        client.aclose = AsyncMock()

        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="tok",  # noqa: S106
            client=client,
        )
        await adapter.destroy_session("sess-123")

        client.delete.assert_awaited_once()
        self.assertIn("/api/v1/sessions/sess-123", client.delete.await_args.args[0])


# ── write_files tests ────────────────────────────────────────────────


class WriteFilesTests(unittest.IsolatedAsyncioTestCase):
    async def test_write_files_chunks_large_file(self) -> None:
        """大于 48KB 的文件应分块写入。"""
        adapter = OnlyboxesSandboxAdapter(base_url="http://fake", access_token="tok")  # noqa: S106
        calls: list[dict] = []

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            calls.append({"url": url, "body": kwargs.get("json", {})})
            return _terminal_ok_response()

        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(side_effect=mock_post)

        data = b"x" * (48 * 1024 + 1000)  # slightly larger than one chunk
        result = await adapter.write_files({"big.bin": data}, base_dir="/mnt/data")

        self.assertTrue(result.success)
        # At least 2 terminal calls: mkdir+truncate + at least 1 chunk
        self.assertGreaterEqual(len(calls), 2)
        # All requests go through /api/v1/commands/terminal
        for call in calls:
            self.assertIn("/api/v1/commands/terminal", call["url"])

        # Verify base64 chunking: at least one call should contain base64 pipe
        b64_calls = [c for c in calls if "base64 -d" in c["body"].get("command", "")]
        self.assertGreaterEqual(len(b64_calls), 2)  # 49152 bytes → 2 chunks

    async def test_write_files_url_uses_curl(self) -> None:
        """URL 类型的文件应生成 curl 命令。"""
        adapter = OnlyboxesSandboxAdapter(base_url="http://fake", access_token="tok")  # noqa: S106
        calls: list[dict] = []

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            calls.append({"url": url, "body": kwargs.get("json", {})})
            return _terminal_ok_response()

        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(side_effect=mock_post)

        result = await adapter.write_files(
            {"data.csv": "https://example.com/data.csv"},
            base_dir="/mnt/data",
        )

        self.assertTrue(result.success)
        # Should have a curl command
        curl_calls = [c for c in calls if "curl" in c["body"].get("command", "")]
        self.assertEqual(len(curl_calls), 1)
        self.assertIn("https://example.com/data.csv", curl_calls[0]["body"]["command"])

    async def test_write_files_mixed_url_and_bytes(self) -> None:
        """Mixed URL and bytes files should use both strategies."""
        adapter = OnlyboxesSandboxAdapter(base_url="http://fake", access_token="tok")  # noqa: S106
        calls: list[dict] = []

        async def mock_post(url: str, **kwargs: Any) -> MagicMock:
            calls.append({"url": url, "body": kwargs.get("json", {})})
            return _terminal_ok_response()

        adapter._client = MagicMock()
        adapter._client.post = AsyncMock(side_effect=mock_post)

        result = await adapter.write_files(
            {
                "remote.csv": "https://example.com/data.csv",
                "local.bin": b"small",
            },
            base_dir="/mnt/data",
        )

        self.assertTrue(result.success)
        curl_calls = [c for c in calls if "curl" in c["body"].get("command", "")]
        b64_calls = [c for c in calls if "base64 -d" in c["body"].get("command", "")]
        self.assertEqual(len(curl_calls), 1)
        self.assertGreaterEqual(len(b64_calls), 1)

    async def test_write_files_empty_dict(self) -> None:
        """Empty files dict should succeed without any terminal calls."""
        adapter = OnlyboxesSandboxAdapter(base_url="http://fake", access_token="tok")  # noqa: S106
        client = AsyncMock()
        client.post = AsyncMock()
        client.aclose = AsyncMock()
        adapter._client = client

        result = await adapter.write_files({})

        self.assertTrue(result.success)
        client.post.assert_not_awaited()


# ── run_in_session tests ─────────────────────────────────────────────


class RunInSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_in_session_uses_session_id(self) -> None:
        """run_in_session should pass session_id in terminal body."""
        response = MagicMock()
        response.status_code = 200
        response.text = json.dumps({"exit_code": 0, "stdout": "ok", "stderr": ""})
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client.aclose = AsyncMock()

        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="tok",  # noqa: S106
            client=client,
        )
        result = await adapter.run_in_session("sess-abc", "print(1)")

        self.assertTrue(result.success)
        # All calls should carry the session_id
        for call in client.post.await_args_list:
            body: dict[str, Any] = call.kwargs["json"]
            self.assertEqual(body["session_id"], "sess-abc")


# ── parse_terminal_response artifact harvest tests ──────────────────


class ParseTerminalResponseHarvestTests(unittest.TestCase):
    """parse_terminal_response() should call strip_artifacts() — ADR-0046 alignment."""

    def _make_response(self, stdout: str, exit_code: int = 0) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.text = json.dumps({"exit_code": exit_code, "stdout": stdout, "stderr": ""})
        resp.ok = True
        return resp

    def test_harvests_artifact_block_from_stdout(self) -> None:
        from lca.layer0_infra.sandbox.onlyboxes_bootstrap import parse_terminal_response
        from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

        stdout = "result: 42\n" + _artifact_block([("report.pdf", b"%PDF-1.4...")])
        emitter = SandboxStreamEmitter("inv_test")
        result = parse_terminal_response(self._make_response(stdout), emitter)

        self.assertTrue(result.success)
        self.assertEqual(len(result.generated_files), 1)
        self.assertEqual(result.generated_files[0].name, "report.pdf")
        self.assertEqual(result.generated_files[0].data, b"%PDF-1.4...")
        # stdout should be cleaned (artifact block removed)
        self.assertIn("result: 42", result.stdout)
        self.assertNotIn(ARTIFACT_BEGIN, result.stdout)

    def test_no_artifact_block_is_safe_noop(self) -> None:
        from lca.layer0_infra.sandbox.onlyboxes_bootstrap import parse_terminal_response
        from lca.layer0_infra.sandbox.streaming import SandboxStreamEmitter

        emitter = SandboxStreamEmitter("inv_test")
        result = parse_terminal_response(self._make_response("hello world\n"), emitter)

        self.assertTrue(result.success)
        self.assertEqual(result.generated_files, ())
        self.assertEqual(result.stdout, "hello world\n")


# ── execute_code artifact scanner tests ──────────────────────────────


class ExecuteCodeArtifactTests(unittest.IsolatedAsyncioTestCase):
    """execute_code() should inject artifact scanner and capture generated files."""

    async def test_scanner_injected_in_code(self) -> None:
        """The code passed to the sandbox should contain the artifact scanner."""
        from lca.layer0_infra.sandbox.artifact_scanner import GUEST_ARTIFACT_SCANNER

        self.assertIn("/mnt/data/outputs", GUEST_ARTIFACT_SCANNER)
        self.assertIn("__LCA_ONLYBOXES_ARTIFACTS__", GUEST_ARTIFACT_SCANNER)


if __name__ == "__main__":
    unittest.main()
