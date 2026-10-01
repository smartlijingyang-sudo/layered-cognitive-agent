"""Session cognitive emit tests (gate.decided.v1 / context.manifested.v1 / brain.think)."""

from __future__ import annotations

import pytest

from lca.cognition.brain.decision_gates.chained.chained import record_gate_decided
from lca.contracts.harness.fold.perceive import (
    fold_context_manifest_from_events,
    fold_gate_decisions_from_events,
)
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.policy.budget import create_budget
from lca.contracts.models.core.policy.gate_policy import GateDecided, PolicyFact
from lca.contracts.models.core.state.state import AgentState
from lca.infrastructure.session.emit.cognitive_emit import (
    emit_context_manifested_for_state,
    emit_gate_decided_from_policy,
    run_reasoner_generate_thoughts_with_spine_facts,
)
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


def _state(*, step: int = 0) -> AgentState:
    return AgentState(
        trace_id="trace:cognitive-emit",
        task="test",
        budget=create_budget(max_steps=8),
        step=step,
    )


def test_emit_gate_decided_from_policy_appends_session_fact() -> None:
    session = Session("gate_emit")
    token = set_publish_session(session)
    try:
        state = _state(step=2)
        emit_gate_decided_from_policy(
            state,
            GateDecided(
                event_id="gate-1",
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
                policy_fact=PolicyFact(
                    kind="repeat_tool_call",
                    message="warning",
                    source="repeat_tool_call",
                ),
            ),
        )
        events = [event for event in session.snapshot_events() if event.type == "gate.decided.v1"]
        assert len(events) == 1
        folded = fold_gate_decisions_from_events(session.snapshot_events(), step=2)
        assert len(folded) == 1
        assert folded[0].gate == "RepeatToolCallGate"
    finally:
        reset_publish_session(token)


def test_record_gate_decided_appends_session_fact() -> None:
    session = Session("gate_record")
    token = set_publish_session(session)
    try:
        state = _state(step=1)
        record_gate_decided(
            state,
            GateDecided(
                event_id="gate-2",
                gate="ToolLoopBreakerGate",
                verdict="rewrite",
                is_rewritten=True,
                tool_name="runCommand",
                rationale="blocked",
                policy_fact=PolicyFact(
                    kind="tool_loop_break",
                    message="stopped",
                    source="tool_loop_breaker",
                ),
            ),
        )
        events = [event for event in session.snapshot_events() if event.type == "gate.decided.v1"]
        assert len(events) == 1
    finally:
        reset_publish_session(token)


def test_emit_gate_decided_noop_when_session_unbound() -> None:
    state = _state()
    assert (
        emit_gate_decided_from_policy(
            state,
            GateDecided(
                event_id="gate-3",
                gate="RepeatToolCallGate",
                verdict="warn",
                is_rewritten=False,
            ),
        )
        is None
    )




def test_emit_context_manifested_for_state_serializes_items() -> None:
    session = Session("manifest_items")
    token = set_publish_session(session)
    try:
        state = _state(step=4)
        manifest = ContextManifest(
            items=(
                ContextItem(
                    kind="policy_fact",
                    payload="loop warning",
                    provenance="repeat_tool_call",
                    extra={"kind": "repeat_tool_call", "gate": "RepeatToolCallGate"},
                ),
            ),
            digest="abc123",
        )
        emit_context_manifested_for_state(state, manifest)
        folded = fold_context_manifest_from_events(session.snapshot_events(), step=4)
        assert folded is not None
        assert len(folded.items) == 1
        assert folded.items[0].kind == "policy_fact"
        assert folded.items[0].provenance == "repeat_tool_call"
    finally:
        reset_publish_session(token)




@pytest.mark.asyncio
async def test_run_reasoner_generate_thoughts_emits_prompt_assembler_eps() -> None:
    from lca.cognition.brain.reasoner.reasoner import PromptReasoner
    from lca.contracts.models.cognition.prompt_assembly import (
        PromptTemplate,
        PromptTemplateProvider,
        PromptTemplateSelector,
        SectionReference,
    )
    from lca.contracts.models.core.conversation.llm import LLMResponse
    from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
    from lca.contracts.protocols import LLMAdapter

    class _NoopLLM(LLMAdapter):
        async def complete(self, prompt: str, **kwargs: object) -> LLMResponse:
            return LLMResponse(text="ok", model="test")

        def stream(self, prompt: str, **kwargs: object):
            async def _gen():
                if False:
                    yield None
                return

            return _gen()

    template = PromptTemplate(
        id="react_prompt",
        variant="react",
        sections=(SectionReference(name="role", kind="pure"),),
    )

    class _StubProvider(PromptTemplateProvider):
        def __init__(self, tpl: PromptTemplate) -> None:
            self._tpl = tpl

        def get_template(self, template_id: str):
            return self._tpl if template_id == self._tpl.id else None

        def list_templates(self):
            return ((self._tpl.id, self._tpl),)

    class _StubRegistry:
        def __init__(self, sections: dict | None = None) -> None:
            self._sections = sections or {}

        def register(self, section, *, kind, name):
            pass

        def resolve(self, *, kind, name):
            return self._sections.get((name, kind))

        def list_sections(self):
            return ()

    class _StaticRole:
        name = "role"

        def render(self, *, role_profile, tools):
            from lca.contracts.models.cognition.prompt_assembly import SectionOutput

            return SectionOutput(text="ROLE_BLOCK")

    class _StubSelector(PromptTemplateSelector):
        def select(self, *, state):
            return ("react_prompt", "profile_default")

    class _AssemblerWrapper:
        template_provider = _StubProvider(template)

        def get_template(self, template_id):
            return self.template_provider.get_template(template_id)

        def list_templates(self):
            return self.template_provider.list_templates()

        def render(self, **kwargs):
            from lca.cognition.brain.sections.assembler import (
                SectionManifestPromptAssembler,
            )

            return SectionManifestPromptAssembler(
                registry=_StubRegistry({("role", "pure"): _StaticRole()}),
                template_provider=_StubProvider(template),
                strip_empty_fields=True,
            ).render(**kwargs)

    class _SeamReasoner(PromptReasoner):
        """Adapt PromptReasoner to the spine seam duck-typed contract.

        run_reasoner_generate_thoughts_with_spine_facts requires a
        role_profile attribute plus complete_turn(state, render);
        PromptReasoner itself keeps no role state (SRP) and takes
        per-turn tools explicitly, so the test supplies both here.
        """

        role_profile = RoleProfile(
            role="reasoner",
            goal="test goal",
            backstory="test backstory",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )

        async def complete_turn(self, state: AgentState, render: object) -> LLMResponse:
            return await super().complete_turn(state, render, tools=())


    session = Session("reasoner_spine")
    token = set_publish_session(session)
    try:
        state = _state()
        reasoner = _SeamReasoner(
            llm=_NoopLLM(),
            selector=_StubSelector(),
            template_provider=_StubProvider(template),
            section_registry=_StubRegistry({("role", "pure"): _StaticRole()}),
        )
        response = await run_reasoner_generate_thoughts_with_spine_facts(reasoner, state)
        assert response.text == "ok"
        starts = [
            event
            for event in session.snapshot_events()
            if event.type == "spine.cognition.prompt_assembler.assemble.start"
        ]
        ends = [
            event
            for event in session.snapshot_events()
            if event.type == "spine.cognition.prompt_assembler.assemble.end"
        ]
        reason_starts = [
            event
            for event in session.snapshot_events()
            if event.type == "spine.cognition.reasoner.reason.start"
        ]
        reason_ends = [
            event
            for event in session.snapshot_events()
            if event.type == "spine.cognition.reasoner.reason.end"
        ]
        assert len(starts) == 1
        assert len(ends) == 1
        assert len(reason_starts) == 1
        assert len(reason_ends) == 1
        assert ends[0].data["payload"]["outcome"] == "success"
        assert reason_ends[0].data["payload"]["outcome"] == "success"
    finally:
        reset_publish_session(token)
