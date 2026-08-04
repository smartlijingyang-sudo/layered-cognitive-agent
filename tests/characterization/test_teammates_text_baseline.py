"""Characteristic baseline for teammates rendering and lead awareness cognition.

Teammates live on TeamAwareness; settlement is its optional component.
PromptReasoner is shape-agnostic: awareness renders itself into prompt vars.
"""

from __future__ import annotations

from lca.contracts.agent_spec import DEFAULT_DELEGATE_MAX_ATTEMPTS
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.run_context import RunContext
from lca.contracts.state import AgentState, Budget
from lca.contracts.team_awareness import Settlement, TeamAwareness
from lca.layer1_cognitive.brain.reasoner import build_teammates_text
from lca.layer1_cognitive.member_status import InMemoryMemberStatus


def _make_profile(role: str, goal: str = "test") -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=goal,
        backstory="",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _awareness(
    teammates: list[RoleProfile] | None = None,
) -> TeamAwareness:
    roles = tuple(p.role for p in (teammates or [])) or ("member",)
    return TeamAwareness(
        teammates=list(teammates or []),
        settlement=Settlement(
            member_status=InMemoryMemberStatus(role_order=roles),
            max_attempts=DEFAULT_DELEGATE_MAX_ATTEMPTS,
        ),
    )


class TestBuildTeammatesTextRendering:
    """Pin the exact string output of build_teammates_text."""

    def test_empty_list_returns_placeholder(self) -> None:
        assert build_teammates_text([]) == "(无可用队友)"

    def test_single_member(self) -> None:
        profiles = [_make_profile("coder", "write code")]
        text = build_teammates_text(profiles)
        assert text == "- role: coder | goal: write code"

    def test_multiple_members(self) -> None:
        profiles = [
            _make_profile("coder", "write code"),
            _make_profile("reviewer", "review code"),
        ]
        text = build_teammates_text(profiles)
        assert text == "- role: coder | goal: write code\n- role: reviewer | goal: review code"

    def test_format_is_consistent(self) -> None:
        """Every line follows '- role: {r} | goal: {g}' format."""
        profiles = [
            _make_profile("a", "ga"),
            _make_profile("b", "gb"),
            _make_profile("c", "gc"),
        ]
        text = build_teammates_text(profiles)
        lines = text.split("\n")
        for line, p in zip(lines, profiles, strict=True):
            assert line == f"- role: {p.role} | goal: {p.goal}"


class TestRunContextAwareness:
    """RunContext carries optional team awareness, not flat team fields."""

    def test_run_context_carries_awareness(self) -> None:
        profiles = [_make_profile("coder", "write code")]
        ctx = RunContext(team_awareness=_awareness(profiles))
        assert ctx.team_awareness is not None
        assert len(ctx.team_awareness.teammates) == 1
        assert ctx.team_awareness.teammates[0].role == "coder"

    def test_run_context_default_has_no_awareness(self) -> None:
        ctx = RunContext()
        assert ctx.team_awareness is None
        assert not hasattr(ctx, "role_mode")
        assert not hasattr(ctx, "teammates")


class TestAgentStateAwareness:
    """AgentState uses the team_awareness slot for lead team cognition."""

    def test_agent_state_awareness_field(self) -> None:
        profiles = [_make_profile("coder", "write code")]
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            team_awareness=_awareness(profiles),
        )
        assert state.team_awareness is not None
        assert len(state.team_awareness.teammates) == 1
        assert state.team_awareness.teammates[0].role == "coder"

    def test_agent_state_default_no_awareness(self) -> None:
        state = AgentState(trace_id="t1", task="test", budget=Budget())
        assert state.team_awareness is None
        assert not hasattr(state, "role_mode")
        assert not hasattr(state, "teammates")


class TestPromptReasonerSolo:
    """Without awareness the reasoner renders the plain role prompt."""

    async def test_solo_prompt_only(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from lca.layer1_cognitive.brain.reasoner import PromptReasoner

        llm = MagicMock()
        llm.complete = AsyncMock(return_value="ok")
        reasoner = PromptReasoner(
            llm=llm,
            role_profile=_make_profile("solo", "work"),
            tools_desc="(no tools)",
            templates={"react_prompt": "just {task}"},
        )
        state = AgentState(trace_id="t1", task="test", budget=Budget())
        await reasoner.generate_thoughts(state, n=1)
        assert llm.complete.called
        assert "just test" in llm.complete.call_args[0][0]


class TestPromptReasonerAwareness:
    """With awareness the reasoner merges awareness vars and its default template."""

    async def test_teammates_injected_from_awareness(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from lca.layer1_cognitive.brain.reasoner import PromptReasoner

        llm = MagicMock()
        llm.complete = AsyncMock(return_value="ok")
        reasoner = PromptReasoner(
            llm=llm,
            role_profile=_make_profile("lead", "manage"),
            tools_desc="(no tools)",
            templates={"hierarchical_prompt": "{teammates} | {member_status_text}"},
        )
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            team_awareness=_awareness([_make_profile("coder", "write code")]),
        )
        await reasoner.generate_thoughts(state, n=1)
        prompt = llm.complete.call_args[0][0]
        assert "coder" in prompt
        assert "write code" in prompt

    async def test_active_template_override(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from lca.layer1_cognitive.brain.reasoner import PromptReasoner

        llm = MagicMock()
        llm.complete = AsyncMock(return_value="ok")
        reasoner = PromptReasoner(
            llm=llm,
            role_profile=_make_profile("lead", "manage"),
            tools_desc="(no tools)",
            templates={
                "hierarchical_prompt": "HIER",
                "custom": "CUSTOM {task}",
            },
        )
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            team_awareness=_awareness([_make_profile("coder")]),
            active_template="custom",
        )
        await reasoner.generate_thoughts(state, n=1)
        assert llm.complete.call_args[0][0] == "CUSTOM test"
