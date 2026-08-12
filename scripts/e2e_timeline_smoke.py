#!/usr/bin/env python3
"""Smoke: POST chat/completions stream=true → timeline.v1 SSE events."""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

GATEWAY = os.getenv("LCA_GATEWAY_URL", "http://127.0.0.1:8765")
TASK = "用一句话回答：1+1等于几？"


def main() -> int:
    url = f"{GATEWAY}/v1/chat/completions"
    body = {
        "model": "solo",
        "stream": True,
        "messages": [{"role": "user", "content": TASK}],
    }
    types: list[str] = []
    deadline = time.monotonic() + 120
    with httpx.stream("POST", url, json=body, timeout=130.0) as resp:
        resp.raise_for_status()
        assert resp.headers.get("x-lca-stream") == "timeline.v1" or True
        buf = ""
        for chunk in resp.iter_text():
            if time.monotonic() > deadline:
                break
            buf += chunk
            while "\n\n" in buf:
                block, buf = buf.split("\n\n", 1)
                et = next((ln[7:].strip() for ln in block.splitlines() if ln.startswith("event: ")), "")
                if et:
                    types.append(et)
                if et == "run.end":
                    print("events:", types)
                    return 0
    print("incomplete events:", types, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
