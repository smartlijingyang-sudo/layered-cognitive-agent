"""Characteristic baseline for teammates_text rendering and routing.

Updated for Phase C: uses role_mode + teammates structured fields instead
of the deprecated teammates_text field. The rendering is now lazy (in
Reasoner), not at assembly time.
"""

from __future__ import annotations

from lca.contracts.enums import RoleMode
from lca.contracts.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.run_context import RunContext
from lca.contracts.state import AgentState, Budget
from lca.layer1_cognitive.brain.reasoner import build_teammates_text


def _make_profile(role: str, goal: str = "test") -> RoleProfile:
    return RoleProfile(
        role=role,
        goal=goal,
        backstory="",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
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


class TestRunContextStructuredFields:
    """Verify RunContext carries role_mode and teammates."""

    def test_run_context_carries_role_mode(self) -> None:
        ctx = RunContext(role_mode=RoleMode.SUPERVISOR)
        assert ctx.role_mode == RoleMode.SUPERVISOR

    def test_run_context_carries_teammates(self) -> None:
        profiles = [_make_profile("coder", "write code")]
        ctx = RunContext(teammates=profiles, role_mode=RoleMode.SUPERVISOR)
        assert len(ctx.teammates) == 1
        assert ctx.teammates[0].role == "coder"

    def test_run_context_default_solo(self) -> None:
        ctx = RunContext()
        assert ctx.role_mode == RoleMode.SOLO
        assert ctx.teammates == []


class TestAgentStateStructuredFields:
    """Verify AgentState uses role_mode + teammates, not teammates_text."""

    def test_agent_state_role_mode_field(self) -> None:
        state = AgentState(
            trace_id="t1", task="test", budget=Budget(), role_mode=RoleMode.SUPERVISOR
        )
        assert state.role_mode == RoleMode.SUPERVISOR

    def test_agent_state_teammates_field(self) -> None:
        profiles = [_make_profile("coder", "write code")]
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            role_mode=RoleMode.SUPERVISOR,
            teammates=profiles,
        )
        assert len(state.teammates) == 1
        assert state.teammates[0].role == "coder"

    def test_agent_state_default_solo(self) -> None:
        state = AgentState(trace_id="t1", task="test", budget=Budget())
        assert state.role_mode == RoleMode.SOLO
        assert state.teammates == []


class TestAgentStateTeammatesTextCompatProperty:
    """The deprecated teammates_text @property renders from structured data."""

    def test_empty_teammates_returns_empty_string(self) -> None:
        import warnings

        state = AgentState(trace_id="t1", task="test", budget=Budget())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert state.teammates_text == ""

    def test_non_empty_teammates_renders_text(self) -> None:
        import warnings

        profiles = [
            _make_profile("coder", "write code"),
            _make_profile("reviewer", "review code"),
        ]
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            role_mode=RoleMode.SUPERVISOR,
            teammates=profiles,
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert state.teammates_text == (
                "- role: coder | goal: write code\n- role: reviewer | goal: review code"
            )

    def test_property_emits_deprecation_warning(self) -> None:
        import warnings

        state = AgentState(trace_id="t1", task="test", budget=Budget())
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _ = state.teammates_text
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)


class TestReasonerTemplateRouting:
    """Verify _resolve_template uses role_mode to pick template.

    Phase C behavior:
    - role_mode != SOLO → "hierarchical_prompt"
    - role_mode == SOLO → "react_prompt"
    - state.active_template takes precedence over both
    """

    def _make_reasoner(self) -> ...:
        from unittest.mock import MagicMock

        from lca.layer1_cognitive.brain.reasoner import SimpleReasoner

        return SimpleReasoner(
            llm=MagicMock(),
            role_profile=_make_profile("supervisor", "manage"),
            tools_desc="(no tools)",
            templates={"react_prompt": "react", "hierarchical_prompt": "hier"},
        )

    def test_solo_routes_to_react(self) -> None:
        reasoner = self._make_reasoner()
        state = AgentState(trace_id="t1", task="test", budget=Budget(), role_mode=RoleMode.SOLO)
        assert reasoner._resolve_template(state) == "react_prompt"

    def test_supervisor_routes_to_hierarchical(self) -> None:
        reasoner = self._make_reasoner()
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            role_mode=RoleMode.SUPERVISOR,
            teammates=[_make_profile("coder", "write code")],
        )
        assert reasoner._resolve_template(state) == "hierarchical_prompt"

    def test_member_routes_to_hierarchical(self) -> None:
        reasoner = self._make_reasoner()
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            role_mode=RoleMode.MEMBER,
        )
        assert reasoner._resolve_template(state) == "hierarchical_prompt"

    def test_active_template_overrides(self) -> None:
        reasoner = self._make_reasoner()
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            role_mode=RoleMode.SUPERVISOR,
            teammates=[_make_profile("coder", "write code")],
            active_template="custom",
        )
        assert reasoner._resolve_template(state) == "custom"


class TestReasonerPromptVariableInjection:
    """Verify teammates are rendered into prompt variables when not solo."""

    async def test_teammates_var_present_when_supervisor(self) -> None:
        from unittest.mock import AsyncMock, MagicMock

        from lca.layer1_cognitive.brain.reasoner import SimpleReasoner

        llm = MagicMock()
        llm.complete = AsyncMock(return_value="ok")
        reasoner = SimpleReasoner(
            llm=llm,
            role_profile=_make_profile("supervisor", "manage"),
            tools_desc="(no tools)",
            templates={"hierarchical_prompt": "{teammates} {teammates_text} {member_status_text}"},
        )
        state = AgentState(
            trace_id="t1",
            task="test",
            budget=Budget(),
            role_mode=RoleMode.SUPERVISOR,
            teammates=[_make_profile("coder", "write code")],
        )
        await reasoner.generate_candidates(state, n=1)
        assert llm.complete.called

    async def test_teammates_var_absent_when_solo(self) -> None:
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
        state = AgentState(trace_id="t1", task="test", budget=Budget(), role_mode=RoleMode.SOLO)
        await reasoner.generate_candidates(state, n=1)
        assert llm.complete.called
