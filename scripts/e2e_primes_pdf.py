#!/usr/bin/env python3
"""E2E smoke: primes PDF via gateway solo run (Journal live SSE)."""

from __future__ import annotations

import os
import sys
import time

import httpx

GATEWAY = os.getenv("LCA_GATEWAY_URL", "http://127.0.0.1:8765")
TASK = (
    "写一个 Python 程序找出 200 以内所有素数，"
    "把 PDF 写到 /mnt/data/outputs/primes_under_200.pdf 解释算法逻辑。"
    "完成后简要说明结果。"
)


def main() -> int:
    create = httpx.post(
        f"{GATEWAY}/runs",
        json={"model": "solo", "messages": [{"role": "user", "content": TASK}]},
        timeout=30.0,
    )
    create.raise_for_status()
    run_id = create.json()["run_id"]
    types: list[str] = []
    deadline = time.monotonic() + 600
    with httpx.stream(
        "GET",
        f"{GATEWAY}/runs/{run_id}/live",
        headers={"Last-Event-ID": "0"},
        timeout=610.0,
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
                    print("ok: ToolStarted count", sum(1 for t in types if t == "ToolStarted"))
                    return 0
    print("incomplete:", types, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
