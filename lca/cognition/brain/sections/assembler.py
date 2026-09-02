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

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from lca.cognition.brain.sections.types import join_lines, strip_empty_labeled_lines
from lca.contracts.models.cognition.prompt_assembly import (
    MissingPromptSectionError,
    PromptSectionRegistry,
    PromptTemplate,
    PromptTemplateProvider,
    PromptTrace,
    PureSection,
    SectionOutput,
    SectionReference,
    SectionTrace,
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
    """The default assembler — concatenates section output verbatim.

    Returns ``(prompt_text, PromptTrace)`` per ADR-0175 D2 so the caller
    (Reasoner) can publish a structured section breakdown to the
    model-visible writer without re-rendering.
    """

    registry: PromptSectionRegistry
    template_provider: PromptTemplateProvider
    strip_empty_fields: bool
    catalog_provider: Callable[[], object] | None = None
    """Optional callable returning the active ``BrainPromptCatalog`` for
    available_skills_count extraction. When ``None`` the assembler
    reports 0 (compatible with tests that don't wire a catalog)."""

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
    ) -> tuple[str, PromptTrace]:
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
            selector_decision_path=getattr(state, "_selector_decision_path", "legacy"),
            catalog=self._catalog(),
        )

    def _catalog(self) -> object | None:
        if self.catalog_provider is None:
            return None
        try:
            return self.catalog_provider()
        except Exception:
            return None


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
    selector_decision_path: str = "legacy",
    catalog: object | None = None,
) -> tuple[str, PromptTrace]:
    """Render one template through the given registry.

    Returns ``(prompt_text, PromptTrace)`` per ADR-0175 D2. The trace
    contains per-section metadata and the joined prompt so that
    ``model_visible/step_<NN>/system_prompt_sections.json`` can be
    reconstructed without re-rendering.

    ``registry`` is optional because the legacy
    ``ReasonerTemplateCatalog.templates()`` shape returned a flat string
    per template id; the back-compat helper
    :func:`templates_from_provider` calls this with ``registry=None``
    so each section's ``SectionOutput.text`` is omitted (empty body) and
    the trace's ``system_prompt_text`` is the empty-joined string.
    """

    pieces: list[str] = []
    section_traces: list[SectionTrace] = []
    for ref in template.sections:
        if registry is None:
            section_traces.append(
                SectionTrace(
                    name=ref.name,
                    kind=ref.kind,
                    optional=ref.optional,
                    used_fallback=False,
                    skipped_empty=True,
                    text_chars=0,
                    text="",
                )
            )
            pieces.append("")
            continue
        section = registry.resolve(kind=ref.kind, name=ref.name)
        if section is None:
            if ref.optional and ref.fallback is not None:
                section_traces.append(
                    SectionTrace(
                        name=ref.name,
                        kind=ref.kind,
                        optional=ref.optional,
                        used_fallback=True,
                        skipped_empty=False,
                        text_chars=len(ref.fallback),
                        text=ref.fallback,
                    )
                )
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
        skipped = output.text == "" and not output.used_fallback and strip_empty_fields
        section_traces.append(
            SectionTrace(
                name=ref.name,
                kind=ref.kind,
                optional=ref.optional,
                used_fallback=output.used_fallback,
                skipped_empty=skipped,
                text_chars=len(output.text),
                # ADR-0176 D3 §2:section 实际渲染正文一并落 trace,
                # 而不是事后手动拼;replay 可零 token 重建。
                text=output.text,
            )
        )
        if skipped:
            continue
        pieces.append(output.text)
    text = join_lines(pieces)
    if strip_empty_fields:
        text = strip_empty_labeled_lines(text)
    activated_skill_ids = tuple(s.skill_id for s in activated_skills)
    tools_count = sum(1 for _ in tools)
    available_skills_count = _catalog_skill_count(catalog)
    trace = PromptTrace(
        template_id=template.id,
        variant=template.variant,
        selector_decision_path=selector_decision_path,
        sections=tuple(section_traces),
        total_chars=len(text),
        activated_skill_ids=activated_skill_ids,
        tools_count=tools_count,
        available_skills_count=available_skills_count,
        system_prompt_text=text,
    )
    return text, trace


def _catalog_skill_count(catalog: object | None) -> int:
    """Count entries advertised by the catalog's brain-skills renderer.

    Tries ``installed_skills`` first (ModelPromptCatalog), then falls
    back to ``render_brain_skills()`` line count, then to 0 when no
    catalog or no introspectable shape is available.
    """
    if catalog is None:
        return 0
    installed = getattr(catalog, "installed_skills", None)
    if installed is not None:
        try:
            return len(installed)
        except TypeError:
            pass
    return 0


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
            raise TypeError(f"section {ref.name!r} does not implement PureSection")
        if role_profile is None:
            return SectionOutput(text="")
        return section.render(role_profile=role_profile, tools=tools)
    if ref.kind == "stateful":
        if not isinstance(section, StatefulSection):
            raise TypeError(f"section {ref.name!r} does not implement StatefulSection")
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
