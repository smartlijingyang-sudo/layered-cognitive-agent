"""Tests for the ADR-0175 trace shape returned by ``render_template``.

These tests pin the structural contract: every render returns
``(prompt_text, PromptTrace)``; the trace carries per-section metadata
so the model-visible writer can serialize without re-rendering.
"""

from __future__ import annotations

from lca.cognition.brain.sections.assembler import (
    SectionManifestPromptAssembler,
    render_template,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplate,
    PromptTemplateProvider,
    PromptTrace,
    SectionKind,
    SectionReference,
    SectionTrace,
)


class _StubProvider(PromptTemplateProvider):
    """Returns a fixed PromptTemplate."""

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
        self._sections[(name, kind)] = section

    def resolve(self, *, kind, name):
        return self._sections.get((name, kind))

    def list_sections(self):
        return tuple((k, n, s) for (n, k), s in sorted(self._sections.items()))


class _StaticSection:
    name = "static"

    def render(self, *, role_profile, tools):
        from lca.contracts.models.cognition.prompt_assembly import SectionOutput

        return SectionOutput(text="static-text")


class _EmptySection:
    name = "empty"

    def render(self, *, role_profile, state, awareness, manifest, tools, activated_skills):
        from lca.contracts.models.cognition.prompt_assembly import SectionOutput

        return SectionOutput(text="")


def test_render_template_returns_prompt_and_trace():
    template = PromptTemplate(
        id="react_prompt",
        variant="react",
        sections=(
            SectionReference(name="role", kind="pure", optional=False),
            SectionReference(name="empty", kind="stateful", optional=True, fallback=""),
        ),
    )
    registry = _StubRegistry(
        {
            ("role", "pure"): _StaticSection(),
            ("empty", "stateful"): _EmptySection(),
        }
    )
    prompt, trace = render_template(
        template=template,
        registry=registry,
        role_profile=_role_profile(),
        strip_empty_fields=True,
    )
    assert isinstance(prompt, str)
    assert "static-text" in prompt
    assert isinstance(trace, PromptTrace)
    assert trace.template_id == "react_prompt"
    assert trace.variant == "react"
    assert len(trace.sections) == 2
    assert all(isinstance(s, SectionTrace) for s in trace.sections)
    assert trace.sections[0].name == "role"
    assert trace.sections[0].kind == "pure"
    assert trace.sections[0].used_fallback is False
    assert trace.sections[0].text_chars == len("static-text")
    assert trace.sections[1].name == "empty"
    assert trace.sections[1].skipped_empty is True
    assert trace.sections[1].text_chars == 0
    assert trace.selector_decision_path == "legacy"


def test_render_template_optional_fallback_marks_used_fallback():
    template = PromptTemplate(
        id="react_prompt",
        variant="react",
        sections=(
            SectionReference(
                name="missing",
                kind="pure",
                optional=True,
                fallback="fb-text",
            ),
        ),
    )
    registry = _StubRegistry({})
    prompt, trace = render_template(
        template=template,
        registry=registry,
        role_profile=_role_profile(),
    )
    assert "fb-text" in prompt
    assert trace.sections[0].used_fallback is True
    assert trace.sections[0].text_chars == len("fb-text")
    assert trace.sections[0].skipped_empty is False


def test_section_manifest_prompt_assembler_returns_tuple_with_template_id():
    template = PromptTemplate(
        id="react_prompt",
        variant="react",
        sections=(SectionReference(name="role", kind="pure"),),
    )
    registry = _StubRegistry({("role", "pure"): _StaticSection()})
    assembler = SectionManifestPromptAssembler(
        registry=registry,
        template_provider=_StubProvider(template),
        strip_empty_fields=True,
    )

    prompt, trace = assembler.render(
        template_id="react_prompt",
        role_profile=_role_profile(),
        state=None,  # type: ignore[arg-type]
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )
    assert prompt == "static-text"
    assert trace.template_id == "react_prompt"
    assert trace.total_chars == len(prompt)


def _role_profile():
    from lca.contracts.models.team.role_team import (
        RoleProfile,
        ToolPermissionManifest,
    )

    return RoleProfile(
        role="r",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


# ── ADR-0176 D3 regressions ─────────────────────────────


def test_section_trace_text_field_carries_section_body() -> None:
    """ADR-0176 D3 §2:SectionTrace.text 携带 section 实际渲染正文。

    直接构造 SectionTrace + 验证 text 字段,frozen dataclass 可序列化。
    """
    from lca.contracts.models.cognition.prompt_assembly import SectionTrace

    trace = SectionTrace(
        name="static",
        kind="pure",
        optional=False,
        used_fallback=False,
        skipped_empty=False,
        text_chars=25,
        text="hello from static section",
    )
    assert trace.text == "hello from static section"
    assert trace.text_chars == len(trace.text)

def test_section_trace_text_equals_zero_when_registry_none() -> None:
    """ADR-0176 D3 §2:registry=None 时(text="")占位。"""
    from lca.cognition.brain.sections.assembler import render_template
    from lca.contracts.models.cognition.prompt_assembly import (
        PromptTemplate,
        SectionReference,
    )

    template = PromptTemplate(
        id="t1",
        variant="react",
        sections=(SectionReference(name="x", kind="pure"),),
    )
    _, trace = render_template(template=template, registry=None)
    assert trace.sections[0].text == ""
    assert trace.sections[0].text_chars == 0
