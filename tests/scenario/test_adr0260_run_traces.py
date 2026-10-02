"""ADR-0260 §4: 轨迹级验收 T2/T3 (nightly / 手动).

运行方式 (252, 仓库根):
  LCA_TRACE_RUN_T2=traces/runs/run_0058acd971e7 \\
  LCA_TRACE_RUN_T3=traces/runs/run_1750eae8f997 \\
  pytest tests/scenario/test_adr0260_run_traces.py
未设环境变量时对应用例 skip,不影响 CI.只读现有轨迹,不起 live run.

T2 (ADR-0260 §4): 冷门事实问答 run 轨迹 — 首轮回答前必须出现 memory_search
调用;直接答对但无检索记录 = 不合格.与 backlog todo-2 合并执行.
指定 run: run_0058acd971e7
("请问:我的姓名、职位、当前技术栈偏好是什么?另外我还有没有架构设计
三原则的记录?") — step 1 即 memory_search,run completed.

T3 (ADR-0260 §4): 易变事实场景 — 轨迹中必须出现重验证工具调用,仅凭记忆
断言 = 不合格.1658 个现有轨迹中无价格/档期问答,以"今日新闻"(日级易变
事实)+ search 重验证为代表场景.
指定 run: run_1750eae8f997 ("今天有什么新闻") — step 1 即 search,
run completed.

解析策略是防御式的:读 journal.json 的 steps[].tool_calls,不依赖 spine
payload 精确结构,避免 traces 格式漂移导致误报.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

import pytest

RUN_T2 = os.environ.get("LCA_TRACE_RUN_T2", "")
RUN_T3 = os.environ.get("LCA_TRACE_RUN_T3", "")
needs_t2 = pytest.mark.skipif(not RUN_T2, reason="需要 LCA_TRACE_RUN_T2=traces/runs/<run_id>")
needs_t3 = pytest.mark.skipif(not RUN_T3, reason="需要 LCA_TRACE_RUN_T3=traces/runs/<run_id>")


def _run_dir(run: str) -> pathlib.Path:
    return pathlib.Path(run)


def _journal(run: str) -> dict:
    return json.loads((_run_dir(run) / "journal.json").read_text(encoding="utf-8"))


def _manifest(run: str) -> dict:
    return json.loads((_run_dir(run) / "manifest.json").read_text(encoding="utf-8"))


def _narrative_title(run: str) -> str:
    head = (_run_dir(run) / "journal.narrative.md").read_text(encoding="utf-8")[:2000]
    m = re.search(r"# Run Narrative —— (.+)", head)
    return m.group(1).strip() if m else ""


def _tool_call_steps(run: str, tool_name: str) -> list[int]:
    """返回调用过 tool_name 的 step_index 列表."""
    out: list[int] = []
    for s in _journal(run).get("steps", []):
        tcs = s.get("tool_calls") or ([s["tool_call"]] if s.get("tool_call") else [])
        for tc in tcs:
            if (tc.get("name") or tc.get("tool")) == tool_name:
                out.append(s["step_index"])
                break
    return out


def _last_step_index(run: str) -> int:
    steps = _journal(run).get("steps", [])
    return max(s["step_index"] for s in steps) if steps else -1


@needs_t2
def test_t2_cold_fact_qa_searches_memory_before_answer():
    """T2: 冷门事实问答 — 首轮回答前必须有 memory_search 调用."""
    title = _narrative_title(RUN_T2)
    assert "姓名" in title and "架构设计三原则" in title, f"指定 run 非冷门事实问答: {title!r}"
    mem_steps = _tool_call_steps(RUN_T2, "memory_search")
    assert mem_steps, "轨迹中找不到 memory_search 真实工具调用 (仅 prompt 提及不算)"
    assert min(mem_steps) < _last_step_index(RUN_T2), "memory_search 未出现在最终回答之前"
    assert _manifest(RUN_T2).get("session_status") == "completed"


@needs_t2
def test_t2_no_unclaimed_memory_claim_without_receipt():
    """T2/todo-2: 若回复含"记下了"类宣称,必须有写盘回执先行.

    本指定 run 的回答未作"记下了"类宣称 — 断言"无宣称 ∨ 有回执痕迹",
    宣称出现但无回执即不合格 (C1 写盘确认门).
    """
    text = (_run_dir(RUN_T2) / "journal.narrative.md").read_text(encoding="utf-8")
    claims = [c for c in ("记下了", "已记住", "已记下", "I've noted") if c in text]
    if not claims:
        return  # 未宣称 — 回执义务不触发,合格
    spine = (_run_dir(RUN_T2) / f"{pathlib.Path(RUN_T2).name}.spine.jsonl")
    blob = spine.read_text(encoding="utf-8") if spine.exists() else ""
    assert "claim_right" in blob or "take_claim_right" in blob, (
        f"回复含{claims}类宣称但轨迹无写盘回执痕迹"
    )


@needs_t3
def test_t3_volatile_fact_has_revalidation_tool_call():
    """T3: 易变事实 — 轨迹中必须出现重验证工具调用,仅凭记忆断言不合格."""
    title = _narrative_title(RUN_T3)
    assert "新闻" in title, f"指定 run 非易变事实场景: {title!r}"
    search_steps = _tool_call_steps(RUN_T3, "search")
    assert search_steps, "易变事实场景下轨迹中找不到重验证工具调用 (search)"
    assert min(search_steps) < _last_step_index(RUN_T3), "重验证调用未出现在最终回答之前"
    assert _manifest(RUN_T3).get("session_status") == "completed"
