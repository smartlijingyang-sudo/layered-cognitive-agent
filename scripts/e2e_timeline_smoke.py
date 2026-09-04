#!/usr/bin/env python3
"""Smoke: simulate frontend wire — POST {LCA_FRONTEND_URL}/lca-api/runs then SSE /live.

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
    run_id = create.json()["run_id"]
    types: list[str] = []
    deadline = time.monotonic() + 120
    with httpx.stream(
        "GET",
        f"{FRONTEND_BASE}/lca-api/runs/{run_id}/live",
        headers=_auth_headers({"Last-Event-ID": "0"}),
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
                if et in {"AgentRunFinished", "TeamRunFinished"}:
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
