"""Section / template / output contracts for the prompt assembly seam (cognition L1).

These contracts describe **only the shape of the data** that flows between
the PromptSectionRegistry, PromptTemplateProvider, PromptAssembler, and the
PromptReasoner. They live in :mod:`lca.contracts` so plugins and the cognitive
implementation can both depend on them without crossing a higher layer.

The seam replaces the prompt-rendering surface that previously lived in
``cognition/brain/reasoner.py``. Each section is a small typed provider:
``PureSection`` for static/profile-derived content, ``StatefulSection`` for
content that reads ``AgentState`` / ``TeamAwareness`` / ``ContextManifest``.
The assembler resolves them through the registry, never by re-reading
configuration or recomputing template variables inline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import ClassVar, Literal, Protocol, runtime_checkable

from lca.contracts.models.core.activation import ActivatedSkill
from lca.contracts.models.core.perception import ContextManifest
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.team_awareness import TeamAwareness
from lca.contracts.protocols.runtime.infra import Tool

SectionKind = Literal["pure", "stateful"]
"""Closed vocabulary for the kind of section a section plugin contributes."""


@dataclass(frozen=True, slots=True)
class SectionOutput:
    """A section's rendered output."""

    text: str
    used_fallback: bool = False


@dataclass(frozen=True, slots=True)
class SectionReference:
    """A reference to one section within a template."""

    name: str
    kind: SectionKind
    optional: bool = False
    fallback: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("pure", "stateful"):
            raise MissingSectionKindError(self.name, self.kind)


class MissingSectionKindError(ValueError):
    """Raised when a SectionReference omits its ``kind`` discriminator."""

    def __init__(self, name: str, kind: object) -> None:
        super().__init__(
            f"SectionReference(name={name!r}) requires kind in {{'pure', 'stateful'}}, got {kind!r}"
        )
        self.section_name = name
        self.kind = kind


class MissingPromptSectionError(KeyError):
    """Raised when the assembler cannot find a section in the registry."""

    def __init__(self, name: str, kind: SectionKind) -> None:
        super().__init__(f"prompt section {name!r} ({kind}) is not registered")
        self.section_name = name
        self.kind = kind


PromptTemplateVariant = Literal["react", "hierarchical", "routing", "casting"]


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """An ordered list of section references assembled into a prompt."""

    id: str
    variant: PromptTemplateVariant
    sections: tuple[SectionReference, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        seen: set[tuple[str, SectionKind]] = set()
        duplicates: list[str] = []
        for ref in self.sections:
            key = (ref.name, ref.kind)
            if key in seen:
                duplicates.append(f"{ref.name}/{ref.kind}")
                continue
            seen.add(key)
        if duplicates:
            raise ValueError(
                f"PromptTemplate(id={self.id!r}) contains duplicate section refs: {duplicates}"
            )


@dataclass(frozen=True, slots=True)
class PromptTemplateConfig:
    """Profile-side template override (Pydantic-compatible schema)."""

    id: str
    variant: PromptTemplateVariant
    sections: tuple[SectionReference, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SectionManifest:
    """Profile-side inventory of section providers registered for a run."""

    sections: Mapping[str, str]
    templates: tuple[PromptTemplate, ...]


@dataclass(frozen=True, slots=True)
class SectionTrace:
    """Per-section render trace produced by :class:`PromptAssembler` (ADR-0175 D2).

    Lets the model-visible writer (and tests) reconstruct the structure
    of the prompt without re-rendering or scraping the joined string.
    """

    name: str
    kind: SectionKind
    optional: bool
    used_fallback: bool
    skipped_empty: bool
    text_chars: int


@dataclass(frozen=True, slots=True)
class PromptTrace:
    """Full render trace produced by :class:`PromptAssembler` (ADR-0175 D2).

    ``system_prompt_text`` is the joined string that the brain will hand
    to the LLM; the trace fields are the structural breakdown so that
    ``model_visible/step_<NN>/system_prompt_sections.json`` can be
    reconstructed without re-rendering.
    """

    template_id: str
    variant: PromptTemplateVariant
    selector_decision_path: str
    sections: tuple[SectionTrace, ...]
    total_chars: int
    activated_skill_ids: tuple[str, ...]
    tools_count: int
    available_skills_count: int
    system_prompt_text: str


SelectorDecisionPath = Literal[
    "active_template_override",
    "consult_duty",
    "team_awareness_routing",
    "profile_default",
    "legacy",
]
"""Why a :class:`PromptTemplateSelector` chose the template it did."""


@runtime_checkable
class PureSection(Protocol):
    """A section whose content derives from non-state inputs."""

    name: ClassVar[str]

    def render(
        self,
        *,
        role_profile: RoleProfile,
        tools: Sequence[Tool],
    ) -> SectionOutput: ...


@runtime_checkable
class StatefulSection(Protocol):
    """A section that reads run state and (optionally) team awareness."""

    name: ClassVar[str]

    def render(
        self,
        *,
        role_profile: RoleProfile,
        state: AgentState,
        awareness: TeamAwareness | None,
        manifest: ContextManifest | None,
        tools: Sequence[Tool],
        activated_skills: tuple[ActivatedSkill, ...],
    ) -> SectionOutput: ...


@runtime_checkable
class PromptSectionRegistry(Protocol):
    """Closed-vocabulary registry of section providers keyed by ``(kind, name)``."""

    def register(self, section: object, *, kind: SectionKind, name: str) -> None: ...

    def resolve(self, *, kind: SectionKind, name: str) -> object | None: ...

    def list_sections(self) -> tuple[tuple[SectionKind, str, object], ...]: ...


@runtime_checkable
class PromptTemplateProvider(Protocol):
    """Holds the active template set queried by id."""

    def get_template(self, template_id: str) -> PromptTemplate | None: ...

    def list_templates(self) -> tuple[tuple[str, PromptTemplate], ...]: ...


@runtime_checkable
class PromptTemplateSelector(Protocol):
    """Picks the active template id per AgentState (ADR-0175 D5).

    Selectors may return ``str`` (legacy) or ``tuple[str, str]``
    ``(template_id, decision_path)`` (new). The helper
    :func:`normalize_selector_result` flattens either shape.
    """

    def select(
        self,
        *,
        state: AgentState,
    ) -> str | tuple[str, str]: ...


@runtime_checkable
class PromptAssembler(Protocol):
    """Renders a prompt by walking one ``PromptTemplate``'s section refs.

    The default implementation :class:`SectionManifestPromptAssembler`
    returns the joined prompt **plus** a :class:`PromptTrace` so the
    caller (Reasoner) can publish a structured section breakdown to the
    model-visible writer without re-rendering (ADR-0175 D2).
    """

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
    ) -> str | tuple[str, PromptTrace]: ...


@runtime_checkable
class BrainPromptCatalog(Protocol):
    """模型可见的工具与技能目录。"""

    def render_tools_xml(self) -> str: ...
    def render_brain_skills(self) -> str: ...
    def render_skill_discovery(self) -> str: ...


# Legacy ReasonerTemplateCatalog Protocol preserved for back-compat imports.


@runtime_checkable
class ReasonerTemplateCatalog(Protocol):
    """Legacy Protocol preserved for back-compat imports."""

    def templates(self) -> Mapping[str, str]: ...


def templates_from_provider(provider: PromptTemplateProvider) -> Mapping[str, str]:
    """Render a section-joined prompt per template id for legacy callers."""
    from lca.cognition.brain.sections.assembler import render_template

    out: dict[str, str] = {}
    for tid, _template in provider.list_templates():
        prompt, _trace = render_template(
            template=_template,
            registry=None,
            role_profile=None,  # type: ignore[arg-type]
            state=None,  # type: ignore[arg-type]
            awareness=None,
            manifest=None,
            tools=(),
            activated_skills=(),
        )
    return out


def normalize_selector_result(
    result: str | tuple[str, str],
) -> tuple[str, SelectorDecisionPath]:
    """Flatten ``PromptTemplateSelector.select`` return to ``(template_id, path)``.

    Accepts either the new ``tuple[str, str]`` shape or the legacy ``str``
    shape so older selectors keep working without code changes.
    """
    if isinstance(result, tuple) and len(result) == 2:
        template_id, decision_path = result
        return template_id, _coerce_decision_path(decision_path)
    return result, "legacy"


def _coerce_decision_path(value: object) -> SelectorDecisionPath:
    """Map unknown decision paths to ``"legacy"`` rather than failing."""
    if value in {
        "active_template_override",
        "consult_duty",
        "team_awareness_routing",
        "profile_default",
        "legacy",
    }:
        return value  # type: ignore[return-value]
    return "legacy"


def normalize_assembler_result(
    result: str | tuple[str, PromptTrace],
) -> tuple[str, PromptTrace | None]:
    """Flatten ``PromptAssembler.render`` return.

    Legacy implementations return a bare ``str``; new ones return
    ``(prompt, PromptTrace)``. The helper returns ``(prompt, trace_or_None)``.
    """
    if isinstance(result, tuple) and len(result) == 2:
        return result
    return result, None


__all__ = [
    "BrainPromptCatalog",
    "MissingPromptSectionError",
    "MissingSectionKindError",
    "PromptAssembler",
    "PromptSectionRegistry",
    "PromptTemplate",
    "PromptTemplateConfig",
    "PromptTemplateProvider",
    "PromptTemplateSelector",
    "PromptTemplateVariant",
    "PromptTrace",
    "PureSection",
    "ReasonerTemplateCatalog",
    "SectionKind",
    "SectionManifest",
    "SectionOutput",
    "SectionReference",
    "SectionTrace",
    "SelectorDecisionPath",
    "StatefulSection",
    "normalize_assembler_result",
    "normalize_selector_result",
    "templates_from_provider",
]
