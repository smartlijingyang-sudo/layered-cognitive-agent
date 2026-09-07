"""Shared fixtures for L3 e2e tests.

The kernel is started as a subprocess; tests connect to it via
``LcaGatewayClient``. The kernel is reused across tests in the module.

DEFERRED: per Agent Note
``docs/notes/proposed/contract/2026-09-07-p1-facade-ws-token-todo.md`` and
the PR-3 Task 20 dispatch, the L3 fixture is only run against the LCA
dev stack (``lca-ops infra start``). In a single-host CI run this is
typically not available, so the fixture is gated by an env var and
the test that depends on it is ``pytest.mark.skip``-ed by default.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from typing import Any

import httpx
import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=2.0)
            if r.status_code in (200, 204):
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"kernel did not become healthy at {url}")


@pytest.fixture(scope="module")
def kernel_process() -> dict[str, Any]:
    """Start a real LCA kernel on a free port for the test module.

    Skipped unless ``LCA_E2E_KERNEL=1`` is set — without the env flag
    we never start a subprocess so the test stays <5 s.
    """
    if os.environ.get("LCA_E2E_KERNEL") != "1":
        pytest.skip(
            "LCA_E2E_KERNEL not set; the L3 fixture requires the LCA "
            "dev stack (see docs/notes/proposed/contract/"
            "2026-09-07-p1-facade-ws-token-todo.md)"
        )
    port = _free_port()
    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "-m",
            "lca_kernel",
            "serve",
            "--profile",
            "test-p1",
            "--port",
            str(port),
        ],
        env={**os.environ, "LCA_TEST_PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_health(f"http://127.0.0.1:{port}/health", timeout=30.0)
    except Exception:
        proc.terminate()
        raise
    yield {"base_url": f"http://127.0.0.1:{port}", "port": port}
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture
def lca_client(kernel_process: dict[str, Any]):
    from tests.e2e.p1._lca_gateway_client import LcaGatewayClient

    client = LcaGatewayClient(base_url=kernel_process["base_url"])
    try:
        yield client
    finally:
        import asyncio

        try:
            asyncio.run(client.close())
        except RuntimeError:
            # If the test already drained an event loop, fall back to
            # creating a fresh one. The harness's close() is idempotent.
            pass
