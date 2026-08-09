"""Onlyboxes sandbox adapter + factory (HTTP mocked)."""

from __future__ import annotations

import base64
import json
import os
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from lca.contracts.models.core.sandbox import SANDBOX_MOUNT_ROOT
from lca.layer0_infra.sandbox.factory import resolve_sandbox, sandbox_backend
from lca.layer0_infra.sandbox.onlyboxes_adapter import OnlyboxesSandboxAdapter
from lca.layer0_infra.sandbox.onlyboxes_artifacts import (
    ARTIFACT_BEGIN,
    ARTIFACT_END,
    strip_artifacts,
)
from lca.layer0_infra.sandbox.onlyboxes_bootstrap import (
    _strip_surrogates,
)
from lca.layer0_infra.sandbox.onlyboxes_bootstrap import (
    build_wrapped_code as _build_wrapped_code,
)


def _artifact_block(files: list[tuple[str, bytes]]) -> str:
    payload = [
        {"name": name, "b64": base64.b64encode(data).decode("ascii")} for name, data in files
    ]
    return ARTIFACT_BEGIN + json.dumps(payload) + ARTIFACT_END


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

    def test_wrapped_code_embeds_mounts(self) -> None:
        wrapped = _build_wrapped_code('print("x")', {"input.bin": b"\x00\x01"})
        self.assertIn(SANDBOX_MOUNT_ROOT, wrapped)
        self.assertIn("input.bin", wrapped)
        self.assertIn(ARTIFACT_BEGIN, wrapped)

    def test_strip_surrogates_replaces_lone_surrogates(self) -> None:
        text = "hello\ud800world\udfff"
        cleaned = _strip_surrogates(text)
        self.assertEqual(cleaned, "hello\ufffdworld\ufffd")
        cleaned.encode("utf-8")

    def test_build_wrapped_code_handles_surrogates(self) -> None:
        code = 'print("\ud800")'
        wrapped = _build_wrapped_code(code, None)
        wrapped.encode("utf-8")


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


class OnlyboxesAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_python_exec_success_and_artifacts(self) -> None:
        stdout = "2\n" + _artifact_block([("echo.csv", b"a,b\n")])
        response = MagicMock()
        response.status_code = 200
        response.text = json.dumps(
            {
                "status": "succeeded",
                "result": {"output": stdout, "stderr": "", "exit_code": 0},
            }
        )
        client = AsyncMock()
        client.post = AsyncMock(return_value=response)
        client.aclose = AsyncMock()

        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="obx_token",  # noqa: S106
            client=client,
        )
        result = await adapter.run(
            'print(1+1)\nopen("/mnt/data/outputs/echo.csv","wb").write(b"a,b\\n")',
            files={"in.csv": b"x"},
            invocation_id="sbx_1",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("2", result.stdout)
        self.assertNotIn(ARTIFACT_BEGIN, result.stdout)
        self.assertEqual(len(result.generated_files), 1)
        self.assertEqual(result.generated_files[0].name, "echo.csv")
        self.assertEqual(result.generated_files[0].data, b"a,b\n")

        call_kwargs = client.post.await_args
        self.assertIn("/api/v1/tasks", call_kwargs.args[0])
        body: dict[str, Any] = call_kwargs.kwargs["json"]
        self.assertEqual(body["capability"], "pythonExec")
        self.assertIn("in.csv", body["input"]["code"])

    async def test_rejects_non_python(self) -> None:
        adapter = OnlyboxesSandboxAdapter(
            base_url="http://obx.example",
            access_token="tok",  # noqa: S106
        )
        result = await adapter.run("console.log(1)", language="javascript")
        self.assertFalse(result.success)
        self.assertIn("python only", result.error)

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


if __name__ == "__main__":
    unittest.main()
