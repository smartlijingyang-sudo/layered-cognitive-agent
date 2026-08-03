"""Characteristic baseline for teammates rendering and supervisor cognition.

Teammates live on ConsultationState (supervisor control plane).
SimpleReasoner is team-agnostic; SupervisorReasoner owns hierarchical prompt.
"""

from __future__ import annotations

from lca.contracts.consultation import ConsultationState
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.run_context import RunContext
from lca.contracts.state import AgentState, Budget
from lca.layer1_cognitive.brain.reasoner import build_teammates_text
from lca.layer1_cognitive.member_status import InMemoryMemberStatus


def _make_profile(role: str, goal: str = "test") -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=goal,
        backstory="",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _consultation(
    teammates: list[RoleProfile] | None = None,
) -> ConsultationState:
    roles = tuple(p.role for p in (teammates or [])) or ("member",)
    return ConsultationState(
        member_status=InMemoryMemberStatus(role_order=roles),
        teammates=list(teammates or []),
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


class TestRunContextConsultation:
    """RunContext carries optional consultation, not flat team fields."""

    def test_run_context_carries_consultation(self) -> None:
        profiles = [_make_profile("coder", "write code")]
        ctx = RunContext(consultation=_consultation(profiles))
        assert ctx.consultation is not None
        assert len(ctx.consultation.teammates) == 1
        assert ctx.consultation.teammates[0].role == "coder"

    def test_run_context_default_has_no_consultation(self) -> None:
        ctx = RunContext()
        assert ctx.consultation is None
        assert not hasattr(ctx, "role_mode")
        assert not hasattr(ctx, "teammates")


class TestAgentStateConsultation:
    """AgentState uses consultation namespace for supervisor control plane."""

    def test_agent_state_consultation_field(self) -> None:
        profiles = [_make_profile("coder", "write code")]
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            consultation=_consultation(profiles),
        )
        assert state.consultation is not None
        assert len(state.consultation.teammates) == 1
        assert state.consultation.teammates[0].role == "coder"

    def test_agent_state_default_no_consultation(self) -> None:
        state = AgentState(trace_id="t1", task="test", budget=Budget())
        assert state.consultation is None
        assert not hasattr(state, "role_mode")
        assert not hasattr(state, "teammates")


class TestSimpleReasonerTeamAgnostic:
    """SimpleReasoner never branches on team identity."""

    async def test_solo_prompt_only(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from lca.layer1_cognitive.brain.reasoner import SimpleReasoner

        llm = MagicMock()
        llm.complete = AsyncMock(return_value="ok")
        reasoner = SimpleReasoner(
            llm=llm,
            role_profile=_make_profile("solo", "work"),
            tools_desc="(no tools)",
            templates={"react_prompt": "just {task}"},
        )
        state = AgentState(trace_id="t1", task="test", budget=Budget())
        await reasoner.generate_candidates(state, n=1)
        assert llm.complete.called
        assert "just test" in llm.complete.call_args[0][0]


class TestSupervisorReasonerPrompt:
    """SupervisorReasoner always uses hierarchical template + consultation."""

    async def test_teammates_injected_from_consultation(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from lca.layer1_cognitive.brain.reasoner import SupervisorReasoner

        llm = MagicMock()
        llm.complete = AsyncMock(return_value="ok")
        reasoner = SupervisorReasoner(
            llm=llm,
            role_profile=_make_profile("supervisor", "manage"),
            tools_desc="(no tools)",
            templates={"hierarchical_prompt": "{teammates} | {member_status_text}"},
        )
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            consultation=_consultation([_make_profile("coder", "write code")]),
        )
        await reasoner.generate_candidates(state, n=1)
        prompt = llm.complete.call_args[0][0]
        assert "coder" in prompt
        assert "write code" in prompt

    async def test_requires_consultation(self) -> None:
        from unittest.mock import MagicMock

        import pytest

        from lca.layer1_cognitive.brain.reasoner import SupervisorReasoner

        reasoner = SupervisorReasoner(
            llm=MagicMock(),
            role_profile=_make_profile("supervisor", "manage"),
            tools_desc="(no tools)",
            templates={"hierarchical_prompt": "{teammates}"},
        )
        state = AgentState(trace_id="t1", task="test", budget=Budget())
        with pytest.raises(ValueError, match="consultation"):
            await reasoner.generate_candidates(state, n=1)

    async def test_active_template_override(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from lca.layer1_cognitive.brain.reasoner import SupervisorReasoner

        llm = MagicMock()
        llm.complete = AsyncMock(return_value="ok")
        reasoner = SupervisorReasoner(
            llm=llm,
            role_profile=_make_profile("supervisor", "manage"),
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
            consultation=_consultation([_make_profile("coder")]),
            active_template="custom",
        )
        await reasoner.generate_candidates(state, n=1)
        assert llm.complete.call_args[0][0] == "CUSTOM test"
