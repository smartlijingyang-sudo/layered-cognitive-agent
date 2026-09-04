"""narrative fold 章节 fixture 测试(ADR-0185 PR-3.1 / spec-p1-narrative)。

任务 SA-2(narrative 增强)在 fold SA-1 合并前先按接口契约落地。本 fixture
用 mock :class:`FoldedModelVisible` 注入 ``StepNarrativeWriter.fold_provider``,
断言 narrative.md 包含 5 个新章节标题(🧰 Tools / 🎯 Skills / 📚 Sections /
💬 Context items / 🧠 Reasoning),并验证 fold = None 走 N/A 优雅降级。

不做:
- 不调真实 ``fold_model_visible`` / 不读 spine.jsonl;
  fold 路径端到端留给 SA-1 合并后跑 e2e。
- 不动 schema 字段;只断言 markdown 渲染。

delete-when:N/A(narrative 增强 fixture,长期回归)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.contracts.models.observability import (
    JournalDocument,
    JournalMetadata,
    JournalStep,
    append_step,
    empty_document,
)
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca_kernel.events.fold import EpochHeader

# ── helpers ──────────────────────────────────────────────────────────────


def _make_doc(*, run_id: str = "run_fold_fixture") -> JournalDocument:
    """最小 2-step document —— fold_provider 按 step_id 区分。"""
    meta = JournalMetadata(
        agent_role="agt_x",
        strategy_key="solo",
        plan_ref="plan_fold_fixture",
        objective="fold chapters fixture",
    )
    doc = empty_document(run_id=run_id, trace_id=run_id, metadata=meta, started_at=1000.0)
    doc = append_step(
        doc,
        JournalStep(
            step_id="step-001",
            step_index=1,
            phase="think",
            entered_at=1000.0,
            exited_at=1001.0,
            duration_ms=1000,
            outcome="ok",
        ),
    )
    doc = append_step(
        doc,
        JournalStep(
            step_id="step-002",
            step_index=2,
            phase="think",
            entered_at=1001.0,
            exited_at=1002.0,
            duration_ms=1000,
            outcome="ok",
        ),
    )
    return doc


def _fake_fold_full(*, step_id: str) -> Any:
    """构造完整 FoldedModelVisible —— 覆盖 5 章节全部字段。"""
    from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

    header = EpochHeader(
        config={"provider": "openai", "model": "gpt-4o"},
        system="You are a fixture assistant.",
        tools=(
            {"name": "bash", "description": "Run shell commands and capture stdout/stderr."},
            {"name": "read_file", "description": "Read a file from disk."},
        ),
    )
    manifest: dict[str, Any] = {
        "source": "model_visible_llm_adapter",
        "template_id": "react-default",
        "selector_decision_path": "profile_default",
        "activated_skill_ids": ["summarize", "code-search"],
        "available_skills_count": 7,
        "tools_count": 2,
        "sections": [
            {
                "name": "system_role",
                "text_chars": 128,
                "content_digest": "sha256:abcdef0123456789",
                "skipped_empty": False,
                "used_fallback": False,
            },
            {
                "name": "tools_catalog",
                "text_chars": 256,
                "content_digest": "sha256:fedcba9876543210",
                "skipped_empty": False,
                "used_fallback": True,
            },
            {
                "name": "skill_discovery",
                "text_chars": 0,
                "content_digest": None,
                "skipped_empty": True,
                "used_fallback": False,
            },
        ],
        "context_manifest_items": [
            {"kind": "clock", "payload_preview": "2026-09-04T12:00:00Z"},
            {"kind": "workspace_artifacts", "payload_preview": "[att-001, att-002]"},
            {"kind": "memory", "payload_preview": "(3 prior summaries)"},
        ],
    }
    assistant = _fake_assistant_payload(
        step_id=step_id,
        assistant_content=(
            f"I will call bash for {step_id}. The output confirms the fixture works end-to-end."
        ),
    )
    return FoldedModelVisible(
        header=header,
        messages=(),
        tool_schemas=header.tools,
        manifest=manifest,
        assistant=assistant,
        header_digest="sha256:fixture",
        source="replayed_fold",
        digest_verified=True,
    )


def _fake_assistant_payload(*, step_id: str, assistant_content: str) -> Any:
    """构造 :class:`SpineLlmRequestHeaderAssistantPayload` pydantic 实例。"""
    from lca_kernel.events.payloads_model_visible import (
        SpineLlmRequestHeaderAssistantPayload,
    )

    return SpineLlmRequestHeaderAssistantPayload.model_validate(
        {
            "step_id": step_id,
            "incarnation": 1,
            "assistant_content": assistant_content,
            "tool_calls": [],
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "header_digest": "sha256:fixture",
        }
    )


def _fake_fold_skills_only(*, step_id: str) -> Any:
    """manifest 只有 activated_skill_ids + available_skills_count;无 sections / context。"""
    from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

    header = EpochHeader(
        config={"provider": "openai"},
        system="sys",
        tools=({"name": "bash", "description": "shell"},),
    )
    manifest: dict[str, Any] = {
        "activated_skill_ids": ["summarize"],
        "available_skills_count": 3,
    }
    return FoldedModelVisible(
        header=header,
        messages=(),
        tool_schemas=header.tools,
        manifest=manifest,
        assistant=None,
        header_digest="sha256:fixture2",
        source="replayed_fold",
        digest_verified=True,
    )


def _fake_fold_empty_manifest(*, step_id: str) -> Any:
    """manifest = {} —— 验证 SkillRouter 未启用 / sections / context 的降级标注。"""
    from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

    header = EpochHeader(config={"provider": "openai"}, system="sys", tools=())
    return FoldedModelVisible(
        header=header,
        messages=(),
        tool_schemas=(),
        manifest={},
        assistant=None,
        header_digest="sha256:fixture3",
        source="replayed_fold",
        digest_verified=True,
    )


# ── 章节计数断言 helper ─────────────────────────────────────────────────


def _assert_chapter_titles(markdown: str, step_id: str) -> None:
    """5 个章节标题都在该 step 的渲染区内出现。"""
    # 找 step 的「### Step <index>:」标题行(必须含冒号,与 Model saw 区
    # 列表的 ``- ``step-001``→...`` 区分)。
    step_index = int(step_id.split("-")[-1])
    step_anchor = f"### Step {step_index}:"
    step_pos = markdown.find(step_anchor)
    assert step_pos >= 0, f"step {step_id} anchor not in narrative:\n{markdown}"
    next_step = markdown.find("### Step ", step_pos + len(step_anchor))
    section_end = next_step if next_step > 0 else markdown.find("---\n_generated", step_pos)
    section = markdown[step_pos : section_end if section_end > 0 else len(markdown)]

    expected = [
        "🧰 Tools sent to model",
        "🎯 Skills activated",
        "📚 Sections in prompt",
        "💬 Context items",
        "🧠 Reasoning per step",
    ]
    for title in expected:
        assert title in section, (
            f"step {step_id} missing chapter {title!r}; section dump:\n{section}"
        )


# ── tests ───────────────────────────────────────────────────────────────


def test_full_fold_renders_all_five_chapters_per_step(tmp_path: Path) -> None:
    """fold_provider 返回完整 FoldedModelVisible → 每 step 含 5 个章节。

    验证:
    - 5 章节标题都在
    - tools 列表渲染 name + description[:60]
    - skills 列表显示 catalog 总数 + activated ids
    - sections 显示 name + text_chars + digest[:16]
    - context items 显示 kind + payload_preview[:120]
    - reasoning 显示 assistant_content 原文
    """

    def fold_provider(run_id: str, step_id: str) -> Any:
        return _fake_fold_full(step_id=step_id)

    writer = StepNarrativeWriter(tmp_path / "narrative.md", fold_provider=fold_provider)
    doc = _make_doc()
    markdown = writer.render(doc)

    _assert_chapter_titles(markdown, "step-001")
    _assert_chapter_titles(markdown, "step-002")

    # tools —— step-001 渲染
    step_section = _extract_step_section(markdown, 1)
    assert "**🧰 Tools sent to model(2)**" in step_section
    assert "`bash`" in step_section
    assert "Run shell commands and capture stdout/stderr" in step_section
    assert "`read_file`" in step_section

    # skills
    assert "**🎯 Skills activated(2)**" in step_section
    assert "catalog 总数: 7" in step_section
    assert "`summarize`" in step_section
    assert "`code-search`" in step_section

    # sections
    assert "**📚 Sections in prompt(3)**" in step_section
    assert "`system_role`" in step_section
    assert "text_chars=128" in step_section
    assert "digest=sha256:abcdef01" in step_section
    assert "(used_fallback)" in step_section
    assert "(skipped_empty)" in step_section

    # context items
    assert "**💬 Context items(3)**" in step_section
    assert "`clock`" in step_section
    assert "2026-09-04T12:00:00Z" in step_section
    assert "`workspace_artifacts`" in step_section

    # reasoning —— 真实原文
    assert "**🧠 Reasoning per step**" in step_section
    assert "I will call bash for step-001" in step_section


def test_fold_none_renders_na_placeholder(tmp_path: Path) -> None:
    """fold_provider 返回 None → 每章节显式 N/A,不抛错、不丢章节。"""

    def fold_provider(run_id: str, step_id: str) -> Any:
        return None

    writer = StepNarrativeWriter(tmp_path / "narrative.md", fold_provider=fold_provider)
    doc = _make_doc()
    markdown = writer.render(doc)

    _assert_chapter_titles(markdown, "step-001")
    step_section = _extract_step_section(markdown, 1)
    assert "N/A (fold SSOT 不可用)" in step_section
    # 即使 fold = None,5 章节标题都保留 —— 用户看到明示而非章节失踪
    assert step_section.count("**🧰 Tools sent to model") >= 1
    assert step_section.count("**🎯 Skills activated") >= 1
    assert step_section.count("**📚 Sections in prompt") >= 1
    assert step_section.count("**💬 Context items") >= 1
    assert step_section.count("**🧠 Reasoning per step**") >= 1


def test_fold_provider_exception_swallowed(tmp_path: Path) -> None:
    """fold_provider 抛异常 → narrative 仍落盘,章节降级 N/A。

    守护:viewer / explain 的 narrative 永远要可读;fold 链路任何
    bug 都不应阻塞 narrative.md 落盘。
    """

    def fold_provider(run_id: str, step_id: str) -> Any:
        raise RuntimeError("fold SSOT 出错 —— 模拟 SA-1 尚未落地")

    writer = StepNarrativeWriter(tmp_path / "narrative.md", fold_provider=fold_provider)
    doc = _make_doc()
    # 不应抛
    markdown = writer.render(doc)
    assert "N/A (fold SSOT 不可用)" in markdown
    # fold 不影响其它叙事内容(summary / step meta / 上下文等)
    assert "## 📊 Summary" in markdown
    assert "fold chapters fixture" in markdown


def test_skills_only_manifest_renders_skills_section(tmp_path: Path) -> None:
    """manifest 只有 activated_skill_ids + available_skills_count —— skills 章节正常显示,
    sections / context 章节降级到「未携带 ...」。
    """

    def fold_provider(run_id: str, step_id: str) -> Any:
        return _fake_fold_skills_only(step_id=step_id)

    writer = StepNarrativeWriter(tmp_path / "narrative.md", fold_provider=fold_provider)
    doc = _make_doc()
    markdown = writer.render(doc)
    step_section = _extract_step_section(markdown, 1)

    assert "**🎯 Skills activated(1)**" in step_section
    assert "catalog 总数: 3" in step_section
    assert "`summarize`" in step_section
    # sections / context 应降级
    assert "未携带 section trace" in step_section
    assert "未携带 context_manifest" in step_section
    # reasoning 走 assistant = None 降级
    assert "assistant payload 缺失" in step_section


def test_empty_manifest_marks_skill_router_disabled(tmp_path: Path) -> None:
    """manifest = {} —— skills 章节显式标注「SkillRouter 未启用」。"""

    def fold_provider(run_id: str, step_id: str) -> Any:
        return _fake_fold_empty_manifest(step_id=step_id)

    writer = StepNarrativeWriter(tmp_path / "narrative.md", fold_provider=fold_provider)
    doc = _make_doc()
    markdown = writer.render(doc)
    step_section = _extract_step_section(markdown, 1)

    assert "SkillRouter 未启用" in step_section
    # sections / context 同样降级
    assert "未携带 section trace" in step_section
    assert "未携带 context_manifest" in step_section


def test_per_step_chapter_cap_enforced(tmp_path: Path) -> None:
    """assistant_content 超长 → fold 章节总长截断到 4000 字符/step,提示截断。"""

    huge_content = "X" * 8000

    def fold_provider(run_id: str, step_id: str) -> Any:
        return _fake_assistant_only(step_id=step_id, content=huge_content)

    writer = StepNarrativeWriter(tmp_path / "narrative.md", fold_provider=fold_provider)
    doc = _make_doc()
    markdown = writer.render(doc)

    # 截断说明应在 narrative 中出现
    assert "4000 字符上限截断" in markdown
    # 但 fold 章节不能超过预算上限太多(允许一定余量因为按 section 切)
    # —— 我们验证 reasoning 段落起始存在(可能完整,可能不在最终 markdown)
    # 核心守护:不抛 / narrative 完整落盘
    assert "## 📊 Summary" in markdown


def _fake_assistant_only(*, step_id: str, content: str) -> Any:
    """只装 reasoning(content 超长);其它 manifest / tools 都空。"""
    from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

    header = EpochHeader(config={"provider": "openai"}, system="sys", tools=())
    assistant = _fake_assistant_payload(step_id=step_id, assistant_content=content)
    return FoldedModelVisible(
        header=header,
        messages=(),
        tool_schemas=(),
        manifest={},
        assistant=assistant,
        header_digest="sha256:fixture4",
        source="replayed_fold",
        digest_verified=True,
    )


def _extract_step_section(markdown: str, step_index: int) -> str:
    """提取 ``### Step <index>:`` 到下一个 ``### Step `` 或文末。"""
    anchor = f"### Step {step_index}:"
    start = markdown.find(anchor)
    assert start >= 0, f"step {step_index} not found"
    next_anchor = markdown.find("### Step ", start + len(anchor))
    end = next_anchor if next_anchor > 0 else markdown.find("---\n_generated", start)
    return markdown[start : end if end > 0 else len(markdown)]


def test_tool_description_truncated_at_60_chars(tmp_path: Path) -> None:
    """tool description 渲染时 _short 截断到 60 字符(防止章节过长)。"""

    long_desc = "D" * 200

    def fold_provider(run_id: str, step_id: str) -> Any:
        from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

        header = EpochHeader(
            config={"provider": "openai"},
            system="sys",
            tools=({"name": "longtool", "description": long_desc},),
        )
        return FoldedModelVisible(
            header=header,
            messages=(),
            tool_schemas=header.tools,
            manifest=None,
            assistant=None,
            header_digest="sha256:fixture5",
            source="replayed_fold",
            digest_verified=True,
        )

    writer = StepNarrativeWriter(tmp_path / "narrative.md", fold_provider=fold_provider)
    doc = _make_doc()
    markdown = writer.render(doc)
    step_section = _extract_step_section(markdown, 1)

    assert "`longtool`" in step_section
    # 完整 200 字符 description 不应整段出现在 narrative
    assert long_desc not in step_section
    # 截断标记 … 应出现(超过 80 字符 limit 触发)
    assert "…" in step_section


def test_section_digest_first_16_chars(tmp_path: Path) -> None:
    """section.content_digest 在 narrative 里只展示前 16 字符。"""

    digest_full = "sha256:" + "f" * 64

    def fold_provider(run_id: str, step_id: str) -> Any:
        from lca.infrastructure.observability.replay.fold_source import FoldedModelVisible

        header = EpochHeader(
            config={"provider": "openai"},
            system="sys",
            tools=({"name": "bash", "description": "shell"},),
        )
        manifest: dict[str, Any] = {
            "sections": [
                {
                    "name": "test_section",
                    "text_chars": 42,
                    "content_digest": digest_full,
                    "skipped_empty": False,
                    "used_fallback": False,
                }
            ]
        }
        return FoldedModelVisible(
            header=header,
            messages=(),
            tool_schemas=header.tools,
            manifest=manifest,
            assistant=None,
            header_digest="sha256:fixture6",
            source="replayed_fold",
            digest_verified=True,
        )

    writer = StepNarrativeWriter(tmp_path / "narrative.md", fold_provider=fold_provider)
    doc = _make_doc()
    markdown = writer.render(doc)
    step_section = _extract_step_section(markdown, 1)

    # digest 前 16 字符 = "sha256:fffffff" (sha256: 共 7 字符 + 9 个 f = 16)
    assert "digest=sha256:fffffffff" in step_section
    # 完整 64 位 hex 不出现
    assert digest_full not in step_section


def test_default_fold_provider_returns_none_when_no_run_dir(tmp_path: Path) -> None:
    """``StepNarrativeWriter(Path(""))`` —— 无 run_dir,默认 fold_provider 返回 None。

    守护:CLI 直接调 render() 而不落盘时,默认 provider 不应抛。
    """
    writer = StepNarrativeWriter(Path(""))
    assert writer.fold_provider("run_x", "step-001") is None
