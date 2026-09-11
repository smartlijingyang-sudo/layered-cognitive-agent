"""Characteristic baseline for teammates rendering and lead awareness cognition.

Teammates live on TeamAwareness; consult_duty is its optional component.
PromptReasoner is shape-agnostic: awareness renders itself into prompt vars.

ADR-0220 §6.2 P9 slimmed :class:`PromptReasoner` to a single new-shape
kwarg set and dropped the legacy ``tools_desc`` / ``templates`` /
``generate_thoughts`` path. The pre-section-manifest characterization
cases for those legacy hooks moved into
``tests/scenario/prompt/test_prompt_assembler_integration.py`` (which
exercises the section-manifest assembler end-to-end); this file now
covers only ``build_teammates_text`` + ``TeamAwareness`` plumbing.
"""

from __future__ import annotations

from lca.cognition.brain.reasoner.reasoner import build_teammates_text
from lca.cognition.member_status import InMemoryMemberStatus
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.run.context import RunContext
from lca.contracts.models.team.team.awareness import ConsultDuty, TeamAwareness
from lca.contracts.protocols.journal.spec.spec import DEFAULT_DELEGATE_MAX_ATTEMPTS


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
        consult_duty=ConsultDuty(
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
