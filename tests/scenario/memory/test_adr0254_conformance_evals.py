"""Tier-2 conformance evals (ADR-0254 §6.2) — deterministic replay without an LLM.

The five EVAL-* IDs are covered by driving the shipped prompt sections, the
write-before-reply guard, the side-chat routing, and the dream pipeline. All
assertions run in the normal pytest flow; no live model is required.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from lca.cognition.memory.acknowledgement import guard_reply
from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
from lca.contracts.models.core.conversation.memory import MemoryRecord
from lca.contracts.models.memory.episode import EpisodeFact, ResidualClass
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.cli.commands.ops.memory import _dream_callbacks
from lca.infrastructure.memory.assistant_memory import AssistantMemory
from lca.infrastructure.memory.dream import run_dream
from lca.infrastructure.memory.episode_buffer import EpisodeBuffer
from lca.infrastructure.tools.assistant.memory_tools import MemoryAddTool
from lca.plugins.prompts.sections.memory import (
    MemoryRetrievalSection,
    PrivacyFirewallSection,
)

_MESSAGE = re.compile(r"message:([A-Za-z0-9_-]+)")


def _home_bound_role() -> RoleProfile:
    return RoleProfile(
        role="助手",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        extra={"assistant_home_path": "asst"},
    )


# ── EVAL-RETRIEVAL-DUTY ──────────────────────────────────────────────────


def test_eval_retrieval_duty_prompt_contains_decision_tree() -> None:
    out = MemoryRetrievalSection().render(
        role_profile=_home_bound_role(),
        task="",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    text = out.text
    assert "memory_search" in text
    assert "多角度" in text
    assert "扫常驻文件兜底" in text
    assert "豁免" in text


# ── EVAL-WRITE-BEFORE-REPLY ─────────────────────────────────────────────


def test_eval_write_before_reply_refuses_without_receipt(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    runtime = SimpleNamespace(memory=memory)
    assert guard_reply("好的，已记下。", runtime) == "这条还没有写入记忆文件。我不能说已经记下。"


def test_eval_write_before_reply_allows_after_successful_write(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    memory.upsert(
        MemoryRecord(
            record_id="ok-1",
            content="用户住在杭州",
            memory_type=MemoryLayer.SEMANTIC,
            importance=0.9,
            category=MemoryCategory.FACT,
            dedupe_key="city",
            confidence=1.0,
            metadata={"source": "user"},
        )
    )
    runtime = SimpleNamespace(memory=memory)
    assert guard_reply("好的，已记下。", runtime) == "好的，已记下。"


# ── EVAL-SIDE-CHAT-PRIVACY ──────────────────────────────────────────────


def test_eval_side_chat_privacy_firewall_in_prompt() -> None:
    out = PrivacyFirewallSection().render(
        role_profile=_home_bound_role(),
        task="",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    assert "检索到不等于可透露" in out.text


@pytest.mark.asyncio
async def test_eval_side_chat_privacy_branch_write_does_not_leak(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    add = MemoryAddTool(memory=memory)
    await add.execute({"content": "用户住在杭州", "category": "fact"})
    await add.execute({"content": "公司机密代号: 凤凰", "category": "fact", "branch": "private-1"})
    main_md = (tmp_path / "asst" / "MEMORY.md").read_text(encoding="utf-8")
    branch = (tmp_path / "asst" / "side-chats" / "private-1" / "MEMORY.md").read_text(
        encoding="utf-8"
    )
    assert "凤凰" in branch
    assert "凤凰" not in main_md
    assert "用户住在杭州" in main_md


# ── EVAL-ANTI-HALLUCINATION ─────────────────────────────────────────────


def test_eval_anti_hallucination_terminal_gate_in_prompt() -> None:
    out = MemoryRetrievalSection().render(
        role_profile=_home_bound_role(),
        task="",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    assert "绝不编造" in out.text
    assert "承认缺失并标注不确定性" in out.text


def test_eval_anti_hallucination_no_false_claim_without_write(tmp_path: Path) -> None:
    memory = AssistantMemory(tmp_path / "asst")
    runtime = SimpleNamespace(memory=memory)
    assert (
        guard_reply("我记住了你的偏好。", runtime) == "这条还没有写入记忆文件。我不能说已经记下。"
    )


# ── EVAL-DREAM-ALIGNMENT-SYNTHESIS ─────────────────────────────────────


def _seed_dream_home(tmp_path: Path) -> Path:
    home = tmp_path / "asst"
    (home / "memory" / "episodes").mkdir(parents=True)
    (home / "memory" / "people").mkdir(parents=True)
    (home / "memory" / "people" / "李雷.md").write_text("# 李雷\n\n常驻杭州\n", encoding="utf-8")
    (home / "memory" / "2026-09-30.md").write_text(
        "# 2026-09-30\n\n- 用户偏好短回复\n", encoding="utf-8"
    )
    EpisodeBuffer(home).append(
        EpisodeFact(
            fact_id="ep-1",
            dedupe_key="pref:short_reply",
            category=MemoryCategory.PREFERENCE,
            content="用户偏好短回复",
            residual=ResidualClass.instruction,
            explicit_user_authority=True,
            source_trace_id="trace-1",
            observed_at_ms=1_759_200_000_000,
        )
    )
    return home


def test_eval_dream_alignment_synthesis_citations_are_valid(tmp_path: Path) -> None:
    home = _seed_dream_home(tmp_path)
    now_ms = 1_759_200_000_000
    render, backfill = _dream_callbacks(home)
    run_dream(home, now_ms=now_ms, backfill=backfill, render=render)
    synthesis = home / "dreams" / "alignment" / "derived" / "ALIGNMENT_SYNTHESIS.md"
    text = synthesis.read_text(encoding="utf-8")
    assertions = [line for line in text.splitlines() if line.startswith("- ")]
    assert assertions
    for line in assertions:
        assert _MESSAGE.search(line), line
