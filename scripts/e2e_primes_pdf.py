#!/usr/bin/env python3
"""E2E smoke: primes-under-200 + PDF via gateway solo run (Onlyboxes + SSE)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gateway.projection.openai_sse import OpenAISSEProjector  # noqa: E402

GATEWAY = os.getenv("LCA_GATEWAY_URL", "http://127.0.0.1:8765")
TASK = (
    "写一个 Python 程序找出 200 以内所有素数，"
    "把 PDF 写到 /mnt/data/outputs/primes_under_200.pdf 解释算法逻辑。"
    "完成后简要说明结果。"
)


def _post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(url, json=body, timeout=30.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("expected JSON object response")
    return payload


def _get_json(url: str) -> dict[str, Any]:
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise TypeError("expected JSON object response")
    return payload


def _collect_chat_sse(*, timeout_s: float = 600.0) -> tuple[set[str], list[dict[str, Any]]]:
    """Stream LobeHub-facing chat/completions and collect lca.events types."""
    url = f"{GATEWAY}/v1/chat/completions"
    body = {
        "model": "solo",
        "stream": True,
        "messages": [{"role": "user", "content": TASK}],
    }
    lca_types: set[str] = set()
    execute_results: list[dict[str, Any]] = []
    deadline = time.monotonic() + timeout_s
    with httpx.stream("POST", url, json=body, timeout=timeout_s + 10) as resp:
        resp.raise_for_status()
        buffer = ""
        for chunk in resp.iter_bytes():
            if time.monotonic() > deadline:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                data_line = next((ln for ln in block.splitlines() if ln.startswith("data: ")), None)
                if data_line is None:
                    continue
                payload_raw = data_line[6:].strip()
                if payload_raw == "[DONE]":
                    return lca_types, execute_results
                payload = json.loads(payload_raw)
                for ev in (payload.get("lca") or {}).get("events") or []:
                    ev_type = str(ev.get("type", ""))
                    lca_types.add(ev_type)
                    if ev_type != "tool_result":
                        continue
                    state = ev.get("state") or {}
                    if state.get("code") or state.get("files"):
                        execute_results.append(
                            {
                                "has_code": bool(state.get("code")),
                                "has_files": bool(state.get("files")),
                                "has_stdout": bool(state.get("stdout")),
                                "file_urls": [
                                    f.get("url")
                                    for f in state.get("files") or []
                                    if isinstance(f, dict)
                                ],
                            }
                        )
    return lca_types, execute_results


def _analyze_journal(run_id: str) -> dict[str, int]:
    journal = Path("traces/runs") / f"{run_id}.jsonl"
    stats = {
        "plugin_with_code": 0,
        "files_found": 0,
        "sandbox_deltas": 0,
        "execute_code_calls": 0,
    }
    if not journal.is_file():
        return stats
    for line in journal.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        event_type = rec.get("event_type")
        ev = rec.get("event") or {}
        if event_type == "SandboxOutputDelta":
            stats["sandbox_deltas"] += 1
        if event_type != "ToolInvoked" or ev.get("tool_name") != "execute_code":
            continue
        stats["execute_code_calls"] += 1
        ps = ev.get("plugin_state") or {}
        if ps.get("code"):
            stats["plugin_with_code"] += 1
        files = ev.get("files") or []
        stats["files_found"] += len(files)
        if files:
            print("journal execute_code files:", files)
    return stats


def _replay_lca_types(run_id: str) -> set[str]:
    journal = Path("traces/runs") / f"{run_id}.jsonl"
    if not journal.is_file():
        return set()
    projector = OpenAISSEProjector(chat_id="e2e-replay", model="solo")
    types: set[str] = set()
    for line in journal.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        frame = (
            f"id: {rec['seq']}\nevent: {rec['event_type']}\n"
            f"data: {json.dumps(rec, ensure_ascii=False)}\n\n"
        )
        for chunk in projector.project_frame(frame):
            for ev in (chunk.get("lca") or {}).get("events") or []:
                types.add(str(ev.get("type", "")))
    return types


def main() -> int:
    health = _get_json(f"{GATEWAY}/health")
    if not health.get("llm_available"):
        print("错误: gateway LLM 不可用", file=sys.stderr)
        return 2

    print("streaming chat/completions …")
    try:
        lca_types, execute_results = _collect_chat_sse()
    except httpx.HTTPError as exc:
        print(f"chat/completions 失败: {exc}", file=sys.stderr)
        return 2

    print("lca sse event types (live stream):", sorted(lca_types))
    print("execute_code tool_results:", execute_results)

    # Resolve latest run id from journal mtime
    runs = sorted(Path("traces/runs").glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime)
    run_id = runs[-1].stem if runs else ""
    print("latest journal:", run_id)
    stats = _analyze_journal(run_id) if run_id else {}
    print("journal stats:", stats)

    replay_types = _replay_lca_types(run_id) if run_id else set()
    print("lca types (journal replay):", sorted(replay_types))

    has_execute_result = any(r.get("has_files") and r.get("has_code") for r in execute_results)
    ok = (
        stats.get("files_found", 0) > 0
        and stats.get("plugin_with_code", 0) > 0
        and stats.get("sandbox_deltas", 0) > 0
        and "tool_started" in lca_types
        and "tool_result" in lca_types
        and has_execute_result
    )
    if not ok:
        print("E2E FAILED", file=sys.stderr)
        return 1
    print("E2E OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
