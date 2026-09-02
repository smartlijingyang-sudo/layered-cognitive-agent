"""PromptAssembler — renders a prompt by walking a template's section list.

The assembler is a pure function over a ``PromptTemplate`` and the inputs
the section plugins declared they need. It resolves each
``SectionReference`` through the ``PromptSectionRegistry`` and joins the
resulting section text in template order.

The assembler lives in the cognition layer (L1) because it composes
**section providers** (also L1) using inputs that the Brain already owns.
The plugin wrapper around it (`lca/plugins/prompts/assembler.py`)
injects the registry and template provider at composition time so the
brain factory only knows the ``PromptAssembler`` Protocol.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.cognition.brain.sections.types import join_lines, strip_empty_labeled_lines
from lca.contracts.models.cognition.prompt_assembly import (
    MissingPromptSectionError,
    PromptSectionRegistry,
    PromptTemplate,
    PromptTemplateProvider,
    PureSection,
    SectionOutput,
    SectionReference,
    StatefulSection,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptAssembler as Protocol_,
)
from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.team_awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra import Tool


@dataclass(frozen=True, slots=True)
class SectionManifestPromptAssembler(Protocol_):
    """The default assembler — concatenates section output verbatim."""

    registry: PromptSectionRegistry
    template_provider: PromptTemplateProvider
    strip_empty_fields: bool

    def render(
        self,
        *,
        template_id: str,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> str:
        template = self.template_provider.get_template(template_id)
        if template is None:
            raise MissingPromptSectionError(template_id, "pure")
        return render_template(
            template=template,
            registry=self.registry,
            role_profile=role_profile,
            state=state,
            awareness=awareness,
            manifest=manifest,
            tools=tools,
            activated_skills=activated_skills,
            strip_empty_fields=self.strip_empty_fields,
        )


def render_template(
    *,
    template: PromptTemplate,
    registry: PromptSectionRegistry | None = None,
    role_profile: RoleProfile | None = None,
    state: AgentState | None = None,
    awareness: TeamAwareness | None = None,
    manifest: ContextManifest | None = None,
    tools: Sequence[Tool] = (),
    activated_skills: tuple[ActivatedSkill, ...] = (),
    strip_empty_fields: bool = True,
) -> str:
    """Render one template through the given registry.

    ``registry`` is optional because the legacy
    ``ReasonerTemplateCatalog.templates()`` shape returned a flat string
    per template id; the back-compat helper
    :func:`templates_from_provider` calls this with ``registry=None``
    so each section's ``SectionOutput.text`` is omitted (empty body).
    """

    pieces: list[str] = []
    for ref in template.sections:
        if registry is None:
            pieces.append("")
            continue
        section = registry.resolve(kind=ref.kind, name=ref.name)
        if section is None:
            if ref.optional and ref.fallback is not None:
                pieces.append(ref.fallback)
                continue
            raise MissingPromptSectionError(ref.name, ref.kind)
        output = _dispatch(
            ref,
            section,
            role_profile=role_profile,
            state=state,
            awareness=awareness,
            manifest=manifest,
            tools=tuple(tools),
            activated_skills=activated_skills,
        )
        if (
            output.text == ""
            and not output.used_fallback
            and strip_empty_fields
        ):
            continue
        pieces.append(output.text)
    text = join_lines(pieces)
    if strip_empty_fields:
        text = strip_empty_labeled_lines(text)
    return text


def _dispatch(
    ref: SectionReference,
    section: object,
    *,
    role_profile: RoleProfile | None,
    state: AgentState | None,
    awareness: TeamAwareness | None,
    manifest: ContextManifest | None,
    tools: tuple[Tool, ...],
    activated_skills: tuple[ActivatedSkill, ...],
) -> SectionOutput:
    if ref.kind == "pure":
        if not isinstance(section, PureSection):
            raise TypeError(
                f"section {ref.name!r} does not implement PureSection"
            )
        if role_profile is None:
            return SectionOutput(text="")
        return section.render(role_profile=role_profile, tools=tools)
    if ref.kind == "stateful":
        if not isinstance(section, StatefulSection):
            raise TypeError(
                f"section {ref.name!r} does not implement StatefulSection"
            )
        if role_profile is None or state is None:
            return SectionOutput(text="")
        return section.render(
            role_profile=role_profile,
            state=state,
            awareness=awareness,
            manifest=manifest,
            tools=tools,
            activated_skills=activated_skills,
        )
    raise ValueError(f"unknown section kind: {ref.kind!r}")


__all__ = [
    "SectionManifestPromptAssembler",
    "render_template",
]
