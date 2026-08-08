"""ADR-0044: LocalSandboxAdapter + resolve_sandbox backend switch (mocked SDK)."""

from __future__ import annotations

import os
import sys
import types
import unittest
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from lca.contracts.models.observability.journal import (
    RunScope,
    SandboxOutputDelta,
    StampedEvent,
    run_scope,
)
from lca.layer0_infra.observability import ObservabilityHub, bind
from lca.layer0_infra.sandbox.factory import resolve_sandbox, sandbox_backend
from lca.layer0_infra.sandbox.local_adapter import LocalSandboxAdapter, _sandbox_name


class _Collector:
    def __init__(self) -> None:
        self.received: list[StampedEvent] = []

    def on_event(self, stamped: StampedEvent) -> None:
        self.received.append(stamped)

    def flush(self) -> None:
        return

    def close(self) -> None:
        return


class _FakeEvent:
    def __init__(
        self,
        event_type: str,
        *,
        data: bytes | None = None,
        code: int | None = None,
    ) -> None:
        self.event_type = event_type
        self.data = data
        self.code = code


class _FakeHandle:
    def __init__(self, events: list[_FakeEvent]) -> None:
        self._events = events

    def __aiter__(self) -> _FakeHandle:
        self._iter = iter(self._events)
        return self

    async def __anext__(self) -> _FakeEvent:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


def _install_fake_microsandbox(
    *,
    events: list[_FakeEvent] | None = None,
    write_error: Exception | None = None,
    create_error: Exception | None = None,
) -> MagicMock:
    """Inject a minimal microsandbox stand-in; return the shared fake sandbox instance."""
    stream_events = events or [
        _FakeEvent("stdout", data=b"hello-local\n"),
        _FakeEvent("exited", code=0),
    ]

    fake_fs = MagicMock()
    if write_error is not None:
        fake_fs.write = AsyncMock(side_effect=write_error)
    else:
        fake_fs.write = AsyncMock(return_value=None)

    fake_sandbox = MagicMock()
    fake_sandbox.fs = fake_fs
    fake_sandbox.exec_stream = AsyncMock(return_value=_FakeHandle(stream_events))
    fake_sandbox.stop = AsyncMock(return_value=None)
    fake_sandbox.create_calls: list[tuple[str, dict[str, Any]]] = []

    class _Sandbox:
        @staticmethod
        async def create(name: str, **kwargs: Any) -> MagicMock:
            if create_error is not None:
                raise create_error
            fake_sandbox.create_calls.append((name, kwargs))
            return fake_sandbox

    class _Network:
        @staticmethod
        def none() -> str:
            return "none"

    class _Patch:
        @staticmethod
        def mkdir(path: str, *, mode: int = 0o755) -> dict[str, Any]:
            return {"path": path, "mode": mode}

    mod = types.ModuleType("microsandbox")
    mod.Sandbox = _Sandbox  # type: ignore[attr-defined]
    mod.Network = _Network  # type: ignore[attr-defined]
    mod.Patch = _Patch  # type: ignore[attr-defined]
    sys.modules["microsandbox"] = mod
    return fake_sandbox


class SandboxNameTests(unittest.TestCase):
    def test_empty_invocation_gets_unique_prefix(self) -> None:
        name = _sandbox_name("")
        self.assertTrue(name.startswith("lca-"))
        self.assertLessEqual(len(name.encode("utf-8")), 128)

    def test_sanitizes_and_truncates(self) -> None:
        raw = "inv/with spaces!!" + ("x" * 200)
        name = _sandbox_name(raw)
        self.assertTrue(name.startswith("lca-"))
        self.assertNotIn("/", name)
        self.assertNotIn(" ", name)
        self.assertLessEqual(len(name.encode("utf-8")), 128)


class ResolveSandboxBackendTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("LCA_SANDBOX_BACKEND", None)
        os.environ.pop("E2B_API_KEY", None)

    def test_backend_local_returns_local_adapter(self) -> None:
        os.environ["LCA_SANDBOX_BACKEND"] = "local"
        os.environ.pop("E2B_API_KEY", None)
        sandbox = resolve_sandbox()
        self.assertIsInstance(sandbox, LocalSandboxAdapter)

    def test_backend_mock_returns_mock(self) -> None:
        os.environ["LCA_SANDBOX_BACKEND"] = "mock"
        sandbox = resolve_sandbox()
        assert sandbox is not None
        self.assertEqual(sandbox.name, "mock-sandbox")

    def test_no_key_no_prefer_mock_returns_none(self) -> None:
        os.environ.pop("LCA_SANDBOX_BACKEND", None)
        os.environ.pop("E2B_API_KEY", None)
        with patch(
            "lca.layer0_infra.sandbox.factory.e2b_api_key",
            return_value=None,
        ):
            self.assertIsNone(resolve_sandbox(prefer_mock=False))

    def test_prefer_mock_without_key(self) -> None:
        os.environ.pop("LCA_SANDBOX_BACKEND", None)
        with patch(
            "lca.layer0_infra.sandbox.factory.e2b_api_key",
            return_value=None,
        ):
            sandbox = resolve_sandbox(prefer_mock=True)
        assert sandbox is not None
        self.assertEqual(sandbox.name, "mock-sandbox")

    def test_sandbox_backend_reads_env(self) -> None:
        os.environ["LCA_SANDBOX_BACKEND"] = "LOCAL"
        self.assertEqual(sandbox_backend(), "local")


class LocalSandboxAdapterTests(unittest.IsolatedAsyncioTestCase):
    def tearDown(self) -> None:
        sys.modules.pop("microsandbox", None)

    async def test_rejects_non_python(self) -> None:
        adapter = LocalSandboxAdapter()
        result = await adapter.run("console.log(1)", language="javascript")
        self.assertFalse(result.success)
        self.assertIn("python only", result.error)

    async def test_missing_package_returns_structured_error(self) -> None:
        sys.modules.pop("microsandbox", None)
        import importlib

        original = importlib.import_module

        def _block_msb(name: str, package: str | None = None) -> Any:
            if name == "microsandbox" or name.startswith("microsandbox."):
                raise ImportError("blocked for test")
            return original(name, package)

        adapter = LocalSandboxAdapter()
        with patch("importlib.import_module", side_effect=_block_msb):
            result = await adapter.run("print(1)")
        self.assertFalse(result.success)
        self.assertIn("sandbox-local", result.error)

    async def test_streams_stdout_and_stops_sandbox(self) -> None:
        fake_sb = _install_fake_microsandbox()
        collector = _Collector()
        hub = ObservabilityHub([], journal_projectors=[collector])
        adapter = LocalSandboxAdapter()

        with bind(hub), run_scope(RunScope(trace_id="t", run_id="r", agent_role="dev")):
            result = await adapter.run(
                "print('hello-local')",
                invocation_id="inv-local-1",
            )

        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello-local", result.stdout)

        deltas = [s.event for s in collector.received if isinstance(s.event, SandboxOutputDelta)]
        self.assertGreaterEqual(len(deltas), 1)
        self.assertEqual(deltas[0].stream, "stdout")
        self.assertIn("hello-local", deltas[0].text_delta)

        fake_sb.stop.assert_awaited()
        self.assertEqual(len(fake_sb.create_calls), 1)
        create_name, create_kwargs = fake_sb.create_calls[0]
        self.assertTrue(create_name.startswith("lca-"))
        self.assertEqual(create_kwargs.get("network"), "none")
        self.assertTrue(create_kwargs.get("replace"))

    async def test_failed_event_sets_error(self) -> None:
        _install_fake_microsandbox(
            events=[
                _FakeEvent("failed", data=b"spawn failed", code=127),
            ]
        )
        adapter = LocalSandboxAdapter()
        result = await adapter.run("print(1)", invocation_id="inv-fail")
        self.assertFalse(result.success)
        self.assertEqual(result.exit_code, 127)
        self.assertIn("spawn failed", result.error)

    async def test_streams_stderr_chunks(self) -> None:
        _install_fake_microsandbox(
            events=[
                _FakeEvent("stderr", data=b"warn\n"),
                _FakeEvent("exited", code=0),
            ]
        )
        adapter = LocalSandboxAdapter()
        result = await adapter.run("import sys; print('x', file=sys.stderr)")
        self.assertTrue(result.success)
        self.assertIn("warn", result.stderr)

    async def test_create_exception_surfaces_as_error(self) -> None:
        _install_fake_microsandbox(create_error=RuntimeError("no kvm"))
        adapter = LocalSandboxAdapter()
        result = await adapter.run("print(1)")
        self.assertFalse(result.success)
        self.assertIn("no kvm", result.error)

    async def test_mounts_files_under_input_root(self) -> None:
        fake_sb = _install_fake_microsandbox()
        adapter = LocalSandboxAdapter()
        result = await adapter.run(
            "print(1)",
            files={"data.csv": b"a,b\n1,2\n"},
            invocation_id="inv-mount",
        )
        self.assertTrue(result.success)
        write_calls = fake_sb.fs.write.await_args_list
        paths = [c.args[0] for c in write_calls if c.args]
        self.assertTrue(any(p.endswith("data.csv") for p in paths))
        self.assertTrue(any("/mnt/data/" in p for p in paths))
        _, create_kwargs = fake_sb.create_calls[0]
        self.assertIn("patches", create_kwargs)


if __name__ == "__main__":
    unittest.main()
