"""Characteristic baseline for teammates rendering and lead awareness cognition.

Teammates live on TeamAwareness; consult_duty is its optional component.
PromptReasoner is shape-agnostic: awareness renders itself into prompt vars.
"""

from __future__ import annotations

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.models.team.run_context import RunContext
from lca.contracts.models.team.team_awareness import ConsultDuty, TeamAwareness
from lca.contracts.protocols.spec import DEFAULT_DELEGATE_MAX_ATTEMPTS
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


class _CapturingStreamLLM:
    """Minimal LLM fake: records prompts via stream() (n=1 production path)."""

    def __init__(self, text: str = "ok") -> None:
        self.text = text
        self.prompts: list[str] = []

    async def stream(self, prompt: str, **kwargs: object):
        from lca.contracts.atoms.enums import LLMStreamEventType
        from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent

        self.prompts.append(prompt)
        response = LLMResponse(text=self.text)
        yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)


class TestPromptReasonerSolo:
    """Without awareness the reasoner renders the plain role prompt."""

    async def test_solo_prompt_only(self) -> None:
        from lca.layer1_cognitive.brain.reasoner import PromptReasoner

        llm = _CapturingStreamLLM()
        reasoner = PromptReasoner(
            llm=llm,
            role_profile=_make_profile("solo", "work"),
            tools_desc="(no tools)",
            templates={"react_prompt": "just {task}"},
        )
        state = AgentState(trace_id="t1", task="test", budget=Budget())
        await reasoner.generate_thoughts(state, n=1)
        assert len(llm.prompts) == 1
        assert "just test" in llm.prompts[0]


class TestPromptReasonerAwareness:
    """With awareness the reasoner merges awareness vars and its default template."""

    async def test_teammates_injected_from_awareness(self) -> None:
        from lca.layer1_cognitive.brain.reasoner import PromptReasoner

        llm = _CapturingStreamLLM()
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
        prompt = llm.prompts[0]
        assert "coder" in prompt
        assert "write code" in prompt

    async def test_active_template_override(self) -> None:
        from lca.layer1_cognitive.brain.reasoner import PromptReasoner

        llm = _CapturingStreamLLM()
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
        assert llm.prompts[0] == "CUSTOM test"
