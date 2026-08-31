"""Smoke test: full kernel boot + solo run completion — see ADR-0122
(run_f03bd17f77f1).

Before the fix, every solo run failed with
``RuntimeError: render_system_role: no FileStore in ambient scope`` because
``RunExecutionEnvironment.prepare()`` did not bind ``run_file_store_scope``.
This test boots a kernel in a subprocess, dispatches one solo run via the
public HTTP API, and asserts the run completes (or at least reaches an LLM
turn — we mock LLM is impossible here, so we accept ``working`` ⇏ failed).
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path

import httpx


def test_solo_run_does_not_fail_with_no_filestore_in_ambient_scope(
    tmp_path: Path,
) -> None:
    """Solo run must not fail with the FileStore ambient scope error."""
    log_path = tmp_path / "kernel.log"
    log_fh = log_path.open("w")
    proc = subprocess.Popen(
        [  # noqa: S607 — controlled dev-only invocation
            "uv", "run", "python", "-m", "lca_kernel", "serve",
            "--profile", "profiles/web-standard.yaml",
            "--host", "127.0.0.1", "--port", "18766",
            "--allow-unknown-env",
        ],
        cwd="/home/lichao/layered-cognitive-agent",
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid,
    )
    try:
        # Wait for the kernel to come up.
        ready = False
        for _ in range(90):
            time.sleep(1)
            with contextlib.suppress(Exception):
                r = httpx.get("http://127.0.0.1:18766/health", timeout=2.0)
                if r.status_code == 200:
                    ready = True
                    break
        assert ready, f"kernel never came up; see {log_path}"

        # Dispatch a solo run.
        resp = httpx.post(
            "http://127.0.0.1:18766/runs",
            json={
                "messages": [{"role": "user", "content": "ping"}],
                "model": "solo",
            },
            timeout=10.0,
        )
        assert resp.status_code in (200, 202), resp.text
        run_id = resp.json()["run_id"]
        start = time.monotonic()

        # Poll until terminal.
        status = "working"
        for _ in range(120):
            time.sleep(1)
            g = httpx.get(f"http://127.0.0.1:18766/runs/{run_id}", timeout=2.0)
            d = g.json()
            status = d.get("status")
            if status != "working":
                break
        elapsed = time.monotonic() - start

        # Read the full kernel log to extract the diagnostic.
        log_fh.flush()
        log_text = log_path.read_text()

        # The original bug surfaces as exactly this substring in stderr/log.
        assert "no FileStore in ambient scope" not in log_text, (
            f"Run {run_id} still hits 'no FileStore in ambient scope'; "
            f"final status={status}, error={d.get('error')!r}. "
            f"See {log_path} for full kernel output."
        )

        # Status must not be 'failed' with the canonical "Agent 阶段执行失败" message.
        if status == "failed":
            err = d.get("error") or ""
            assert "Agent 阶段执行失败" not in err, (
                f"Run {run_id} still fails with the generic Chinese error: {err!r}"
            )

        # The original bug completed in ~0.1s (sync RuntimeError). After the fix
        # a real run takes longer (LLM round-trip) — accept >= 1s as evidence
        # the run actually executed instead of short-circuiting.
        assert elapsed >= 1.0, (
            f"Run {run_id} completed in {elapsed:.2f}s — too fast, "
            f"suggests sync failure rather than a real LLM turn. "
            f"final status={status}, error={d.get('error')!r}."
        )
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
        log_fh.close()
