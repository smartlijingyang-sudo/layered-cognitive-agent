#!/usr/bin/env python3
"""Smoke: simulate frontend wire — POST {LCA_FRONTEND_URL}/lca-api/runs then SSE /live.

RETIRED OBSERVATION LEG. ADR-0200 (p1-agent-gateway-bridge) retires the
hand-rolled run SSE transport: ``stream_run_live``, ``LegacyRunDispatcher`` and
the front-end adapters ``lcaRunObserve`` / ``lcaRunHil`` are all in its deletion
table, and ``GET /runs/{id}/live`` is no longer registered. ``stream_run_fold``
is a stub. This script therefore exercises only the command leg end to end; the
live leg exits 2 with a pointer instead of a bare 404 traceback. Re-enable it
when ADR-0200 PR-5 has migrated the driver to the WS gateway, which is the same
condition that re-enables ``tests/scenario/run_4/test_run_then_live.py``.

Mirrors ``LcaRunDriver.ts`` (`deploy/lobehub/patches/runtime/LcaRunDriver.ts`):
the request shape, ``Authorization: Bearer ${LCA_TOKEN}`` and the ``/lca-api/runs``
path prefix that the Next.js rewrite in ``file_proxy_rewrite.py`` strips before
forwarding to the gateway.

Equivalent CLI: ``lca-ops e2e timeline`` (wraps this script with the same envs).

Env:
    LCA_FRONTEND_URL  base of the LobeHub Next app; default ``http://10.36.6.252:3010``.
    LCA_TOKEN         bearer token; default ``lca-local`` (matches the driver default).

The bare gateway port (e.g. ``127.0.0.1:8765/runs``) does not serve this prefix —
set ``LCA_FRONTEND_URL`` to a reachable LobeHub dev/prod host or the request fails
on the rewrite path.
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

FRONTEND_BASE = os.getenv("LCA_FRONTEND_URL", "http://10.36.6.252:3010").rstrip("/")
TOKEN = os.getenv("LCA_TOKEN", "lca-local")
TASK = "用一句话回答：1+1等于几？"

EXIT_LIVE_RETIRED = 2


def _auth_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    if extra:
        headers.update(extra)
    return headers


def main() -> int:
    create = httpx.post(
        f"{FRONTEND_BASE}/lca-api/runs",
        json={
            "agent": {"id": "solo", "name": "助手"},
            "messages": [{"role": "user", "content": TASK}],
            "model": "solo",
        },
        headers=_auth_headers({"Content-Type": "application/json"}),
        timeout=30.0,
    )
    create.raise_for_status()
    body = create.json()
    run_id = body["run_id"]
    print(
        f"command leg ok: POST /lca-api/runs -> 202 "
        f"run_id={run_id} ws_token={'present' if body.get('ws_token') else 'absent'}"
    )

    live_url = f"{FRONTEND_BASE}/lca-api/runs/{run_id}/live"
    probe = httpx.get(live_url, params={"after": 0}, headers=_auth_headers(), timeout=30.0)
    if probe.status_code in (404, 410):
        print(
            f"live leg retired: GET {live_url} -> {probe.status_code}. "
            "ADR-0200 retired the run SSE transport in favour of the WS gateway "
            "(/v1/runs/{run_id}/ws). Re-enable this smoke with ADR-0200 PR-5.",
            file=sys.stderr,
        )
        return EXIT_LIVE_RETIRED
    probe.raise_for_status()

    types: list[str] = []
    deadline = time.monotonic() + 120
    with httpx.stream(
        "GET",
        live_url,
        params={"after": 0},
        headers=_auth_headers(),
        timeout=130.0,
    ) as resp:
        resp.raise_for_status()
        buf = ""
        for chunk in resp.iter_text():
            if time.monotonic() > deadline:
                break
            buf += chunk
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                et = next(
                    (ln[7:].strip() for ln in block.splitlines() if ln.startswith("event: ")),
                    "",
                )
                if et:
                    types.append(et)
                if et == "done":
                    print("live events:", types)
                    return 0
    print("incomplete:", types, file=sys.stderr)
    print(
        json.dumps({"frontend_base": FRONTEND_BASE, "run_id": run_id}, ensure_ascii=False),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
