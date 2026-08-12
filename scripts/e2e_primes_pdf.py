#!/usr/bin/env python3
"""E2E smoke: primes PDF via gateway solo run (timeline.v1 SSE)."""

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
    url = f"{GATEWAY}/v1/chat/completions"
    body = {"model": "solo", "stream": True, "messages": [{"role": "user", "content": TASK}]}
    types: list[str] = []
    deadline = time.monotonic() + 600
    with httpx.stream("POST", url, json=body, timeout=610.0) as resp:
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
                if et == "run.end":
                    print("timeline events:", types)
                    print("ok: tool.* count", sum(1 for t in types if t.startswith("tool.")))
                    return 0
    print("incomplete:", types, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
