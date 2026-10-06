"""Guard-branch coverage for the assemble leg: SectionManifestPromptAssembler.

Complements tests/cognition/test_assembler_section_trace.py (happy path +
fallback + trace shape) with the branches it leaves uncovered:

- render(): unknown template_id -> MissingPromptSectionError
- render(): catalog_provider raising is swallowed -> catalog degrades to None
- render(): available_skills_reason three-state derivation
- render_template(): missing required section / missing optional without fallback
- _dispatch(): section not implementing the declared kind -> TypeError
- render(): selector_decision_path propagated to the trace
"""

from __future__ import annotations

import pytest

from lca.cognition.brain.sections.assembler import (
    SectionManifestPromptAssembler,
    render_template,
)
from lca.contracts.models.cognition.prompt_assembly import (
    MissingPromptSectionError,
    PromptTemplate,
    PromptTemplateProvider,
    SectionOutput,
    SectionReference,
)


class _StubProvider(PromptTemplateProvider):
    """Returns a fixed PromptTemplate (or None for the missing-template case)."""

    def __init__(self, template: PromptTemplate | None) -> None:
        self._template = template

    def get_template(self, template_id: str):
        return self._template

    def list_templates(self):
        return ((self._template.id, self._template),) if self._template else ()


class _StubRegistry:
    def __init__(self, sections: dict[tuple[str, str], object]) -> None:
        self._sections = sections

    def resolve(self, *, kind, name):
        return self._sections.get((name, kind))

    def list_sections(self):
        return tuple((k, n, s) for (n, k), s in sorted(self._sections.items()))


class _StaticSection:
    name = "static"

    def render(self, *, role_profile, tools):
        return SectionOutput(text="static-text")


def _role_profile():
    from lca.contracts.models.team.role.team import (
        RoleProfile,
        ToolPermissionManifest,
    )

    return RoleProfile(
        role="r",
        goal="g",
        backstory="b",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )


def _template(sections=()) -> PromptTemplate:
    return PromptTemplate(id="react_prompt", variant="react", sections=sections)


def _assembler(
    template: PromptTemplate | None = None,
    sections: dict[tuple[str, str], object] | None = None,
    catalog_provider=None,
) -> SectionManifestPromptAssembler:
    return SectionManifestPromptAssembler(
        registry=_StubRegistry(sections or {("static", "pure"): _StaticSection()}),
        template_provider=_StubProvider(template),
        strip_empty_fields=True,
        catalog_provider=catalog_provider,
    )


def _render_kwargs(**overrides):
    kwargs = {
        "role_profile": _role_profile(),
        "task": "",
        "awareness": None,
        "manifest": None,
        "tools": (),
        "activated_skills": (),
    }
    kwargs.update(overrides)
    return kwargs


def test_render_unknown_template_id_raises() -> None:
    assembler = _assembler(template=None)
    with pytest.raises(MissingPromptSectionError) as exc_info:
        assembler.render(template_id="no_such_template", **_render_kwargs())
    assert exc_info.value.section_name == "no_such_template"
    assert exc_info.value.kind == "pure"


def test_render_catalog_provider_error_degrades_to_no_catalog() -> None:
    def _broken_provider():
        raise RuntimeError("catalog env not ready")

    assembler = _assembler(
        template=_template((SectionReference(name="static", kind="pure"),)),
        catalog_provider=_broken_provider,
    )
    prompt, trace = assembler.render(template_id="react_prompt", **_render_kwargs())
    assert prompt == "static-text"
    assert trace.available_skills_count == 0
    assert trace.available_skills_reason == "not_enabled"


def test_render_catalog_skills_present_but_no_activation() -> None:
    class _Catalog:
        installed_skills = ("skill-a", "skill-b", "skill-c")

    assembler = _assembler(
        template=_template((SectionReference(name="static", kind="pure"),)),
        catalog_provider=_Catalog,
    )
    _, trace = assembler.render(template_id="react_prompt", **_render_kwargs())
    assert trace.available_skills_count == 3
    assert trace.available_skills_reason == "no_match"


def test_render_unsized_installed_skills_counts_as_zero() -> None:
    class _Catalog:
        @property
        def installed_skills(self):
            # generator is not sizeable -> len() raises TypeError -> treated as 0
            return (s for s in ("skill-a",))

    assembler = _assembler(
        template=_template((SectionReference(name="static", kind="pure"),)),
        catalog_provider=_Catalog,
    )
    _, trace = assembler.render(template_id="react_prompt", **_render_kwargs())
    assert trace.available_skills_count == 0
    assert trace.available_skills_reason == "not_enabled"


def test_render_activated_skills_reason_activated() -> None:
    from lca.contracts.models.core.workspace.activation import ActivatedSkill

    assembler = _assembler(
        template=_template((SectionReference(name="static", kind="pure"),)),
    )
    _, trace = assembler.render(
        template_id="react_prompt",
        **_render_kwargs(
            activated_skills=(ActivatedSkill(skill_id="s1", name="Skill One"),)
        ),
    )
    assert trace.activated_skill_ids == ("s1",)
    assert trace.available_skills_reason == "activated"


def test_render_template_missing_required_section_raises() -> None:
    registry = _StubRegistry({})
    template = _template((SectionReference(name="gone", kind="pure", optional=False),))
    with pytest.raises(MissingPromptSectionError) as exc_info:
        render_template(
            template=template,
            registry=registry,
            role_profile=_role_profile(),
        )
    assert exc_info.value.section_name == "gone"


def test_render_template_missing_optional_without_fallback_raises() -> None:
    registry = _StubRegistry({})
    template = _template(
        (SectionReference(name="gone", kind="pure", optional=True, fallback=None),)
    )
    with pytest.raises(MissingPromptSectionError):
        render_template(
            template=template,
            registry=registry,
            role_profile=_role_profile(),
        )


def test_dispatch_pure_section_wrong_type_raises_type_error() -> None:
    # registry returns a plain object that does not implement PureSection
    registry = _StubRegistry({("blob", "pure"): object()})
    template = _template((SectionReference(name="blob", kind="pure"),))
    with pytest.raises(TypeError, match="does not implement PureSection"):
        render_template(
            template=template,
            registry=registry,
            role_profile=_role_profile(),
        )


def test_dispatch_stateful_section_wrong_type_raises_type_error() -> None:
    registry = _StubRegistry({("blob", "stateful"): object()})
    template = _template((SectionReference(name="blob", kind="stateful"),))
    with pytest.raises(TypeError, match="does not implement StatefulSection"):
        render_template(
            template=template,
            registry=registry,
            role_profile=_role_profile(),
        )


def test_render_selector_decision_path_propagated_to_trace() -> None:
    assembler = _assembler(
        template=_template((SectionReference(name="static", kind="pure"),)),
    )
    _, trace = assembler.render(
        template_id="react_prompt",
        selector_decision_path="routing",
        **_render_kwargs(),
    )
    assert trace.selector_decision_path == "routing"
