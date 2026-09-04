"""ADR-0175: ``StdReasonerPromptCapture`` writes the real brain prompt.

Plus ContextVar binding round-trip test (Reasoner → LLM adapter).
"""

from __future__ import annotations

import json
from pathlib import Path

from lca.contracts.models.cognition.prompt_assembly import (
    PromptTrace,
    SectionTrace,
)
from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
    bind_current_reasoner_prompt,
    get_current_reasoner_prompt,
    reset_current_reasoner_prompt,
)
from lca.infrastructure.observability.loop_cursor.reasoner_prompt_capture import (
    StdReasonerPromptCapture,
)


def _trace() -> PromptTrace:
    return PromptTrace(
        template_id="react_prompt",
        variant="react",
        selector_decision_path="profile_default",
        sections=(
            SectionTrace(
                name="role",
                kind="pure",
                optional=False,
                used_fallback=False,
                skipped_empty=False,
                text_chars=12,
            ),
            SectionTrace(
                name="goal",
                kind="pure",
                optional=False,
                used_fallback=False,
                skipped_empty=False,
                text_chars=8,
            ),
        ),
        total_chars=20,
        activated_skill_ids=("skill.foo", "skill.bar"),
        tools_count=3,
        available_skills_count=5,
        system_prompt_text="<ROLE>x</ROLE>\n<GOAL>y</GOAL>",
    )


def test_capture_writes_two_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "traces" / "runs" / "rid"
    run_dir.mkdir(parents=True)
    capture = StdReasonerPromptCapture(run_dir=run_dir)
    artifact = capture.capture(step_id="step-001", trace=_trace())

    sp = run_dir / "model_visible" / "step-001" / "system_prompt.json"
    sec = run_dir / "model_visible" / "step-001" / "system_prompt_sections.json"
    assert sp.exists(), "system_prompt.json must be written"
    assert sec.exists(), "system_prompt_sections.json must be written"
    assert artifact.step_id == "step-001"
    assert artifact.system_prompt_path.endswith("system_prompt.json")
    assert artifact.system_prompt_sections_path.endswith("system_prompt_sections.json")
    assert artifact.system_prompt_digest.startswith("sha256:")

    payload = json.loads(sp.read_text(encoding="utf-8"))
    assert payload["step_id"] == "step-001"
    assert payload["template_id"] == "react_prompt"
    assert payload["selector_decision_path"] == "profile_default"
    assert "<ROLE>x</ROLE>" in payload["body"]

    sec_payload = json.loads(sec.read_text(encoding="utf-8"))
    assert sec_payload["activated_skill_ids"] == ["skill.foo", "skill.bar"]
    assert sec_payload["tools_count"] == 3
    assert sec_payload["available_skills_count"] == 5
    assert len(sec_payload["sections"]) == 2
    assert sec_payload["sections"][0]["name"] == "role"


def test_context_var_round_trip() -> None:
    """Reasoner binds, LLM adapter reads, reset clears."""
    from lca.contracts.observability.reasoner_prompt_capture import (
        ReasonerPromptArtifact,
    )

    # Sanity: ReasonerPromptArtifact signature unchanged (it has no body field).
    _ = ReasonerPromptArtifact(
        step_id="x",
        system_prompt_path="a",
        system_prompt_sections_path="b",
        system_prompt_digest="sha256:0",
    )

    token = bind_current_reasoner_prompt(
        type(get_current_reasoner_prompt())  # type: ignore[arg-type]
        if False
        else _make_current_prompt()
    )
    try:
        cp = get_current_reasoner_prompt()
        assert cp is not None
        assert cp.template_id == "react_prompt"
        assert cp.selector_decision_path == "profile_default"
        assert "<ROLE>x</ROLE>" in cp.system_prompt_text
    finally:
        reset_current_reasoner_prompt(token)

    assert get_current_reasoner_prompt() is None


def _make_current_prompt():
    from lca.infrastructure.observability.loop_cursor.reasoner_prompt_binding import (
        CurrentReasonerPrompt,
    )

    return CurrentReasonerPrompt(
        step_id="step-001",
        template_id="react_prompt",
        selector_decision_path="profile_default",
        system_prompt_text="<ROLE>x</ROLE>\n<GOAL>y</GOAL>",
    )


def test_reasoner_binds_prompt_trace_and_context_manifest() -> None:
    """``PromptReasoner._bind_reasoner_prompt`` 把 PromptTrace + ContextManifest 带进 ContextVar。

    LLM 边界(ModelVisibleLLMAdapter)从绑定真值读 ``prompt_trace`` /
    ``context_manifest`` 派生 model_visible 上下文清单(ADR-0167 D3/D4);
    缺省 None 字段保留既有 4 标量构造的有效性。
    """
    from lca.cognition.brain.reasoner import PromptReasoner
    from lca.contracts.models.core.perception import ContextItem, ContextManifest
    from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest

    class _UnusedLLM:
        name = "unused"

        async def complete(self, prompt: str, **kwargs: object) -> object:  # pragma: no cover
            raise AssertionError("llm not used by _bind_reasoner_prompt")

        async def stream(self, prompt: str, **kwargs: object):  # pragma: no cover
            raise AssertionError("llm not used by _bind_reasoner_prompt")
            yield  # pragma: no cover

    reasoner = PromptReasoner(
        llm=_UnusedLLM(),
        role_profile=RoleProfile(
            role="r",
            goal="g",
            backstory="b",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        ),
    )
    trace = _trace()
    manifest = ContextManifest(
        items=(ContextItem(kind="clock", payload="2026-09-04", provenance="clock_sensor"),)
    )

    token = reasoner._bind_reasoner_prompt(trace, manifest)
    try:
        bound = get_current_reasoner_prompt()
        assert bound is not None
        assert bound.system_prompt_text == trace.system_prompt_text
        assert bound.template_id == trace.template_id
        assert bound.prompt_trace is trace
        assert bound.context_manifest is manifest
    finally:
        reset_current_reasoner_prompt(token)

    # manifest 缺席时绑定仍成立,context_manifest 为 None
    token2 = reasoner._bind_reasoner_prompt(trace, None)
    try:
        bound2 = get_current_reasoner_prompt()
        assert bound2 is not None
        assert bound2.prompt_trace is trace
        assert bound2.context_manifest is None
    finally:
        reset_current_reasoner_prompt(token2)


# ── ADR-0176 D3/D4 regressions ────────────────────────────


def test_sections_payload_includes_content_digest(tmp_path: Path) -> None:
    """ADR-0176 D3 §4:content_digest = sha256(text),仅当 text 非空时写。"""
    from lca.contracts.models.cognition.prompt_assembly import (
        PromptTrace,
        SectionTrace,
    )

    run_dir = tmp_path / "run"
    capture = StdReasonerPromptCapture(run_dir=run_dir)
    trace = PromptTrace(
        template_id="t1",
        variant="react",
        selector_decision_path="legacy",
        sections=(
            SectionTrace(
                name="s1",
                kind="pure",
                optional=False,
                used_fallback=False,
                skipped_empty=False,
                text_chars=5,
                text="hello",
            ),
            SectionTrace(
                name="s2",
                kind="pure",
                optional=False,
                used_fallback=False,
                skipped_empty=True,
                text_chars=0,
                text="",
            ),
        ),
        total_chars=5,
        activated_skill_ids=(),
        tools_count=0,
        available_skills_count=0,
        system_prompt_text="hello",
    )
    capture.capture(step_id="step-001", trace=trace)

    sections_path = run_dir / "model_visible" / "step-001" / "system_prompt_sections.json"
    payload = json.loads(sections_path.read_text(encoding="utf-8"))
    sections = payload["sections"]
    # s1 有 text → content_digest
    assert "content_digest" in sections[0]
    assert sections[0]["content_digest"].startswith("sha256:")
    # s2 text 空 → 没有 content_digest
    assert "content_digest" not in sections[1]


def test_messages_overview_system_field_in_capture(tmp_path: Path) -> None:
    """ADR-0176 D4:StdModelVisibleCapture 把 system 数据并入 messages.json.messages_overview。"""
    from lca.infrastructure.observability.loop_cursor.model_visible_capture import (
        StdModelVisibleCapture,
    )

    capture = StdModelVisibleCapture(run_dir=tmp_path / "r")
    artifact = capture.capture(
        step_id="step-001",
        incarnation=1,
        system={"role": "system", "content": "be helpful"},
        tools=[],
        messages=[{"role": "user", "content": "hi"}],
        manifest={"objective": "chat"},
    )
    # system.json 不再存在
    assert not (tmp_path / "r" / "model_visible" / "step-001" / "system.json").exists()
    # messages.json 含 messages_overview.system
    messages_payload = json.loads(
        (tmp_path / "r" / "model_visible" / "step-001" / "messages.json").read_text(
            encoding="utf-8"
        )
    )
    assert "messages_overview" in messages_payload
    assert messages_payload["messages_overview"]["system"]["content"] == "be helpful"
    assert messages_payload["messages"][0]["role"] == "user"
    # artifact.system_path 指向 messages.json
    assert artifact.system_path == "model_visible/step-001/messages.json"
