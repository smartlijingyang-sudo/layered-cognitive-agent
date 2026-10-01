"""ADR-0256 §10:真实 run 的 traces 断言(nightly / 手动).

运行方式:LCA_TRACE_RUN=traces/runs/<run_id> pytest tests/scenario/test_namespace_run_traces.py
未设环境变量时全部 skip,不影响 CI.

解析策略是防御式的:把 spine.jsonl / journal.json 逐行序列化后做文本断言,
不依赖 payload 的精确结构,避免 traces 格式漂移导致误报.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

import pytest

RUN_DIR = os.environ.get("LCA_TRACE_RUN", "")
needs_trace = pytest.mark.skipif(
    not RUN_DIR, reason="需要 LCA_TRACE_RUN=traces/runs/<run_id> 方可运行"
)

CATALOG_LINE_RE = re.compile(r"- ([a-z_]+): ")


def _run_dir() -> pathlib.Path:
    return pathlib.Path(RUN_DIR)


def _manifest() -> dict:
    return json.loads((_run_dir() / "manifest.json").read_text(encoding="utf-8"))


def _all_text() -> str:
    chunks: list[str] = []
    for name in ("spine.jsonl", "journal.json"):
        path = _run_dir() / name
        if path.exists():
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _first_llm_call_text() -> str:
    """首个 llm.call.start 事件的序列化文本(即首 turn prompt)."""
    spine = _run_dir() / "spine.jsonl"
    for line in spine.read_text(encoding="utf-8").splitlines():
        if '"llm.call.start"' in line or "'llm.call.start'" in line:
            return line
    return ""


@needs_trace
def test_e1_first_turn_catalog_has_eight_lines():
    """首 turn prompt 含 8 行目录,无 'N tools:' fallback(验收 1/8)."""
    prompt = _first_llm_call_text()
    assert prompt, "spine.jsonl 里找不到 llm.call.start 事件"
    lines = CATALOG_LINE_RE.findall(prompt)
    assert len(lines) >= 8, f"目录行不足 8 行,实际: {sorted(set(lines))}"
    assert "1 tools:" not in prompt


@needs_trace
def test_e2_defer_chain_tool_search_then_tool():
    """run 内出现 tool_search 加载 -> 工具调用成功的完整 defer 链."""
    text = _all_text()
    assert '"tool_search"' in text or "'tool_search'" in text
    assert _manifest().get("session_status") == "completed"


@needs_trace
def test_e3_block_retry_heal_chain():
    """出现'未加载被拒 -> tool_search -> 重试成功'的自愈链,run 非 failed(验收 4)."""
    text = _all_text()
    assert "namespace_not_loaded" in text or "not loaded" in text
    assert _manifest().get("session_status") != "failed"


@needs_trace
def test_e4_tool_health_all_green():
    """tool 健康全绿,且与 doctor 口径一致(验收 8)."""
    manifest = _manifest()
    health = manifest.get("health_summary", {})
    by_type = health.get("by_type", {})
    assert by_type.get("tool") == "ok", f"tool 健康非 ok: {by_type}"
    assert health.get("conditions_failed", 0) == 0


@needs_trace
def test_e5_no_single_tool_namespace():
    """没有任何 namespace 名等于某个工具名(单工具 namespace 绝迹,验收 8)."""
    prompt = _first_llm_call_text()
    assert prompt, "spine.jsonl 里找不到 llm.call.start 事件"
    namespaces = set(CATALOG_LINE_RE.findall(prompt))
    tool_names = set(re.findall(r'"name":\s*"([a-zA-Z_][a-zA-Z0-9_]*)"', prompt))
    overlap = namespaces & tool_names
    assert not overlap, f"单工具 namespace 仍存在: {overlap}"
