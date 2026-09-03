"""EXECUTION_POINT coverage: ``prompt_assembler.assemble.start`` / ``.end``
must be emitted by :class:`PromptReasoner.generate_thoughts` with the
ADR-0175 payload extensions.

Per ADR-0165 I8, every entry in ``EXECUTION_POINTS`` must have at least
one emitter wired in production. This test pins the wiring for the
two prompt_assembler EPs (which previously had emitters but no callers).

The test captures via a minimal spine stub (mirrors the protocol surface
of :class:`EventSpine`) so it doesn't pull the full EventRecord
validator chain (which requires SpinesContext.get_run() to be set).
"""

from __future__ import annotations

from typing import Any

from lca.cognition.brain.reasoner import PromptReasoner
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplate,
    PromptTemplateProvider,
    PromptTemplateSelector,
    SectionKind,
    SectionReference,
)
from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.protocols import LLMAdapter
from lca.plugins.events.publishers.spine_reflector_cognition import (  # noqa: F401  # ADR-0181 PR-2: 旧 reflector 退役
    ReflectorClass,
)
from lca_kernel.events.mechanism import EventMechanism


class _CapturingMechanism:
    """Stub matching ``EventMechanism.send(...)`` keyword surface (ADR-0181 PR-2)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send(self, payload, *, plugin):  # noqa: ARG002
        self.calls.append(
            {
                "execution_point": payload.execution_point,
                "channel": payload.channel,
                "payload": dict(payload.payload),
            }
        )
        return object()

    def register_sink(self, **kwargs):  # pragma: no cover
        return None

    def subscribe(self, **kwargs):  # pragma: no cover
        return None


class _StubProvider(PromptTemplateProvider):
    def __init__(self, template: PromptTemplate) -> None:
        self._template = template

    def get_template(self, template_id: str):
        return self._template

    def list_templates(self):
        return (("react_prompt", self._template),)


class _StubRegistry:
    def __init__(self, sections: dict[tuple[str, SectionKind], object]) -> None:
        self._sections = sections

    def register(self, section, *, kind, name):
        pass

    def resolve(self, *, kind, name):
        return self._sections.get((name, kind))

    def list_sections(self):
        return ()


class _StaticPure:
    name = "role"

    def render(self, *, role_profile, tools):
        from lca.contracts.models.cognition.prompt_assembly import SectionOutput

        return SectionOutput(text="hello-world")


class _StubStaticSelector(PromptTemplateSelector):
    def select(self, *, state):
        return ("react_prompt", "profile_default")


class _NoopLLM(LLMAdapter):
    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(text="ok", model="test")

    def stream(self, prompt: str, **kwargs: Any):
        async def _gen():
            if False:
                yield None
            return

        return _gen()


def _build_state() -> AgentState:
    from lca.contracts.models.core.lifecycle import TaskStatus
    from lca.contracts.models.core.state import Budget

    return AgentState(
        trace_id="t-001",
        task="hello",
        budget=Budget(),
        step=0,
        activated_skills=[],
        status=TaskStatus.WORKING,
    )


def _make_assembler(template: PromptTemplate, registry):
    from lca.cognition.brain.sections.assembler import (
        SectionManifestPromptAssembler,
    )

    impl = SectionManifestPromptAssembler(
        registry=registry,
        template_provider=_StubProvider(template),
        strip_empty_fields=True,
    )

    class _Wrapper:
        template_provider = impl.template_provider

        def render(self, **kwargs):
            return impl.render(**kwargs)

    return _Wrapper()


async def test_prompt_assembler_eps_emitted_with_payload():
    from lca.contracts.models.team.role_team import (
        ToolPermissionManifest,
    )

    # ADR-0181 PR-2: 旧 _CapturingSpine 退役，新机制走 _CapturingMechanism
    spine = _CapturingMechanism(); EventMechanism.set_default(spine)
    try:
        template = PromptTemplate(
            id="react_prompt",
            variant="react",
            sections=(SectionReference(name="role", kind="pure"),),
        )
        registry = _StubRegistry({("role", "pure"): _StaticPure()})
        assembler = _make_assembler(template, registry)
        role_profile = RoleProfile(
            role="r",
            goal="g",
            backstory="b",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        )
        reasoner = PromptReasoner(
            llm=_NoopLLM(),
            role_profile=role_profile,
            assembler=assembler,
            selector=_StubStaticSelector(),
            tools=[],
        )
        await reasoner.generate_thoughts(_build_state())
    finally:
        EventMechanism.set_default(None)

    starts = [c for c in spine.calls if c["execution_point"] == "prompt_assembler.assemble.start"]
    ends = [c for c in spine.calls if c["execution_point"] == "prompt_assembler.assemble.end"]
    assert len(starts) == 1, f"start EP must be emitted exactly once per render (got {spine.calls})"
    assert len(ends) == 1, f"end EP must be emitted exactly once per render (got {spine.calls})"
    start = starts[0]
    end = ends[0]
    assert start["payload"]["template_id"] == "react_prompt"
    assert start["payload"]["decision_path"] == "profile_default"
    assert start["payload"]["sections"] == ["role"]
    assert end["payload"]["section_count"] == 1
    outputs = end["payload"]["section_outputs"]
    assert isinstance(outputs, list) and len(outputs) == 1
    assert outputs[0]["name"] == "role"
    assert outputs[0]["kind"] == "pure"
    assert outputs[0]["text_chars"] == len("hello-world")
    assert isinstance(end["payload"]["total_chars"], int)
    assert end["payload"]["total_chars"] > 0


def test_skill_router_route_emits_decision_path():
    import asyncio

    from lca.cognition.brain.skill_router import KeywordSkillRouter

    # ADR-0181 PR-2: 旧 _CapturingSpine 退役，新机制走 _CapturingMechanism
    spine = _CapturingMechanism(); EventMechanism.set_default(spine)
    try:
        router = KeywordSkillRouter(
            rules={"research_prompt": ["hello"]},
            default_template="react_prompt",
        )
        result = asyncio.run(router.route(_build_state()))
    finally:
        EventMechanism.set_default(None)

    assert result == "research_prompt"
    skill_eps = [c for c in spine.calls if c["execution_point"] == "skill_router.route"]
    assert len(skill_eps) == 1
    assert skill_eps[0]["payload"]["template"] == "research_prompt"
    assert skill_eps[0]["payload"]["decision_path"] == "keyword_match"


def test_selector_returns_decision_path_tuple():
    from lca.plugins.prompts.selector import TeamAwarenessTemplateSelector

    selector = TeamAwarenessTemplateSelector(default_template="react_prompt")
    state = _build_state()
    template_id, decision_path = selector.select(state=state)
    assert template_id == "react_prompt"
    assert decision_path in {
        "active_template_override",
        "consult_duty",
        "team_awareness_routing",
        "profile_default",
        "legacy",
    }
