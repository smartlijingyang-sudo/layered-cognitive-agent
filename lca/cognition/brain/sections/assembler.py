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

from collections.abc import Callable, Sequence, Sized
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from lca.cognition.brain.sections.types import join_lines, strip_empty_labeled_lines
from lca.contracts.models.cognition.prompt_assembly import (
    AvailableSkillsReason,
    BrainPromptCatalog,
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
from lca.contracts.models.core.perceive.perception import ContextManifest
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.models.team.team.awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra.infra import Tool


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
    catalog_provider: Callable[[], BrainPromptCatalog] | None = None
    """Optional callable returning the active ``BrainPromptCatalog`` for
    available_skills_count extraction. When ``None`` the assembler
    reports 0 (compatible with tests that don't wire a catalog)."""

    def render(
        self,
        *,
        template_id: str,
        role_profile: RoleProfile,
        task: str,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
        selector_decision_path: str = "legacy",
    ) -> tuple[str, PromptTrace]:
        template = self.template_provider.get_template(template_id)
        if template is None:
            raise MissingPromptSectionError(template_id, "pure")
        return render_template(
            template=template,
            registry=self.registry,
            role_profile=role_profile,
            task=task,
            awareness=awareness,
            manifest=manifest,
            tools=tools,
            activated_skills=activated_skills,
            strip_empty_fields=self.strip_empty_fields,
            selector_decision_path=selector_decision_path,
            catalog=self._catalog(),
        )

    def _catalog(self) -> BrainPromptCatalog | None:
        if self.catalog_provider is None:
            return None
        try:
            return self.catalog_provider()
        except Exception:
            # INTENTIONAL: catalog_provider 内部可能因 env / registry 未就绪抛
            # → 视为"无 catalog",回 None 让 caller 走内置默认 sections。
            return None


def render_template(
    *,
    template: PromptTemplate,
    registry: PromptSectionRegistry,
    role_profile: RoleProfile,
    task: str = "",
    awareness: TeamAwareness | None = None,
    manifest: ContextManifest | None = None,
    tools: Sequence[Tool] = (),
    activated_skills: tuple[ActivatedSkill, ...] = (),
    strip_empty_fields: bool = True,
    selector_decision_path: str = "legacy",
    catalog: BrainPromptCatalog | None = None,
) -> tuple[str, PromptTrace]:
    """Render one template through the given registry.

    Returns ``(prompt_text, PromptTrace)`` per ADR-0175 D2. The trace
    contains per-section metadata and the joined prompt so that the
    rendered prompt can be reconstructed without re-rendering
    (ADR-0185 PR-4 后由 spine event bus 承载,不再写旁路文件)。

    Sections read only the arguments below. ``AgentState`` is not one of
    them: the turn's ``ContextManifest`` is the single run-state channel,
    so a section that needs a new fact forces it through the manifest
    instead of reaching into reducer-owned state.
    """

    pieces: list[str] = []
    section_traces: list[SectionTrace] = []
    for ref in template.sections:
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
            task=task,
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
    # ADR-0185 spec §2.4 P4:派生 SkillRouter 决策原因 — truthiness → 闭集值。
    # 三态见 AvailableSkillsReason 定义;assembler 是 trace 上唯一写入者。
    if activated_skill_ids:
        available_skills_reason: AvailableSkillsReason = "activated"
    elif available_skills_count > 0:
        available_skills_reason = "no_match"
    else:
        available_skills_reason = "not_enabled"
    trace = PromptTrace(
        template_id=template.id,
        variant=template.variant,
        selector_decision_path=selector_decision_path,
        sections=tuple(section_traces),
        total_chars=len(text),
        activated_skill_ids=activated_skill_ids,
        tools_count=tools_count,
        available_skills_count=available_skills_count,
        available_skills_reason=available_skills_reason,
        system_prompt_text=text,
    )
    return text, trace


@runtime_checkable
class _SkillInventory(Protocol):
    """Minimal countable shape the assembler needs from a catalog.

    ``BrainPromptCatalog`` (the composition contract) deliberately only
    declares render methods; the skill *count* needs a sizable inventory.
    This protocol is the count seam's declared surface — no getattr
    duck-probing. A catalog that satisfies ``BrainPromptCatalog`` but not
    this shape is a wiring error and fails loud in ``_catalog_skill_count``.
    """

    installed_skills: Sized


def _catalog_skill_count(catalog: BrainPromptCatalog | None) -> int:
    """Count the installed skills advertised by the catalog.

    Derives from the assembler's declared minimal countable shape
    (``_SkillInventory.installed_skills``): ``len()`` when sizable, 0
    when no catalog is wired or the inventory is not sizable.

    fix-doc (RA-094): the previous docstring promised a
    ``render_brain_skills()`` line-count fallback that was never
    implemented. It is deliberately NOT added: rendered display text is
    not a count source — an empty catalog renders the non-empty marker
    "（无可用技能）", which line-counting would report as 1.
    """
    if catalog is None:
        return 0
    if not isinstance(catalog, _SkillInventory):
        # Explicit, not silent 0: a catalog wired here must expose the
        # countable inventory the seam declares.
        raise TypeError(
            "catalog must satisfy the assembler's countable shape "
            f"(_SkillInventory.installed_skills), got {type(catalog).__name__}"
        )
    try:
        return len(catalog.installed_skills)
    except TypeError:
        # INTENTIONAL: installed_skills 是非 size-able 类型(generator / 单值)
        # → 视为 0;catalog 数量统计允许非序列来源。
        return 0


def _dispatch(
    ref: SectionReference,
    section: object,
    *,
    role_profile: RoleProfile,
    task: str,
    awareness: TeamAwareness | None,
    manifest: ContextManifest | None,
    tools: tuple[Tool, ...],
    activated_skills: tuple[ActivatedSkill, ...],
) -> SectionOutput:
    if ref.kind == "pure":
        if not isinstance(section, PureSection):
            raise TypeError(f"section {ref.name!r} does not implement PureSection")
        return section.render(role_profile=role_profile, tools=tools)
    if ref.kind == "stateful":
        if not isinstance(section, StatefulSection):
            raise TypeError(f"section {ref.name!r} does not implement StatefulSection")
        return section.render(
            role_profile=role_profile,
            task=task,
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
