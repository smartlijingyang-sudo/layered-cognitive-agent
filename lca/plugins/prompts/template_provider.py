"""PromptTemplateProvider — Cordis plugin owning the template-collection seam."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.capabilities import PROMPT_TEMPLATE_PROVIDER
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplate as _PromptTemplate,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplateConfig,
    PromptTemplateVariant,
    SectionReference,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplateProvider as Protocol_,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# ── Built-in templates (DSH-style declarative defaults) ──────────────


def _builtin_section_refs() -> tuple[tuple[str, str, bool, str | None], ...]:
    """Plain tuples kept here so this module stays import-cheap.

    Each entry: ``(name, kind, optional, fallback)``.
    """

    return (
        # react_prompt (no-LLM-supplied team sections)
        ("role", "pure", False, None),
        ("goal", "pure", False, None),
        ("backstory", "pure", False, None),
        ("current_date", "stateful", True, None),
        ("tools", "pure", False, None),
        ("available_skills", "pure", False, None),
        ("activated_skills", "stateful", False, None),
        ("task", "stateful", False, None),
        ("prior_conversation", "stateful", False, None),
        ("context", "stateful", False, None),
        # react template's static instruction blocks
        ("react_workflow", "pure", True, ""),
        ("react_tool_usage_guidelines", "pure", True, ""),
        # routing_prompt adds team sections
        ("teammates", "stateful", False, None),
        ("assigned_roles_text", "stateful", False, None),
        ("member_reports_text", "stateful", False, None),
        ("routing_instructions", "pure", True, ""),
        # hierarchical_prompt adds consult-duty sections
        ("member_status_text", "stateful", False, None),
        ("evidence_pack_text", "stateful", True, ""),
        ("hierarchical_instructions", "pure", True, ""),
    )


def _variant_for(name: str) -> PromptTemplateVariant:
    if name == "react_prompt":
        return "react"
    if name == "routing_prompt":
        return "routing"
    if name == "hierarchical_prompt":
        return "hierarchical"
    if name == "casting_prompt":
        return "casting"
    raise ValueError(f"unknown built-in template: {name!r}")


def _builtin_templates() -> Mapping[str, _PromptTemplate]:
    """Built-in templates — the default surface Profile YAML extends."""

    base = _builtin_section_refs()
    def refs(sl):
        return tuple(
            SectionReference(name=n, kind=k, optional=o, fallback=f) for (n, k, o, f) in sl
        )

    react_section_count = 13  # through react_tool_usage_guidelines
    routing_extra = 4  # teammates, assigned_roles, member_reports, routing_instructions
    hierarchical_extra = 4  # member_status, evidence_pack, hierarchical_instructions (+ extra)
    return {
        "react_prompt": _PromptTemplate(
            id="react_prompt",
            variant=_variant_for("react_prompt"),
            sections=refs(base[:react_section_count]),
        ),
        "routing_prompt": _PromptTemplate(
            id="routing_prompt",
            variant=_variant_for("routing_prompt"),
            sections=refs(base[:react_section_count] + base[react_section_count : react_section_count + routing_extra]),
        ),
        "hierarchical_prompt": _PromptTemplate(
            id="hierarchical_prompt",
            variant=_variant_for("hierarchical_prompt"),
            sections=refs(
                base[:react_section_count]
                + base[react_section_count + routing_extra : react_section_count + routing_extra + hierarchical_extra]
            ),
        ),
    }


# ── Provider implementation ──────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _ProviderImpl(Protocol_):
    """Holds the active template set, queried by id."""

    _templates: Mapping[str, _PromptTemplate]

    def get_template(self, template_id: str) -> _PromptTemplate | None:
        return self._templates.get(template_id)

    def list_templates(self) -> tuple[tuple[str, _PromptTemplate], ...]:
        return tuple((tid, self._templates[tid]) for tid in sorted(self._templates))


# ── Config schema ──────────────────────────────────────────────────


class Config(BaseModel):
    """Profile-declared template overrides."""

    model_config = ConfigDict(extra="forbid")
    profile_templates: tuple[PromptTemplateConfig, ...] = Field(default_factory=tuple)
    section_overrides: dict[str, dict[str, object]] = Field(default_factory=dict)


def _build_provider(config: Config) -> _ProviderImpl:
    """Compose built-ins + profile overrides into the runtime provider."""

    merged: dict[str, _PromptTemplate] = dict(_builtin_templates())
    for tpl_cfg in config.profile_templates:
        merged[tpl_cfg.id] = _PromptTemplate(
            id=tpl_cfg.id,
            variant=tpl_cfg.variant,
            sections=tuple(
                SectionReference(
                    name=r.name,
                    kind=r.kind,
                    optional=r.optional,
                    fallback=r.fallback,
                )
                for r in tpl_cfg.sections
            ),
        )
    return _ProviderImpl(_templates=merged)


@plugin(
    id="lca-prompt-template-provider-builtin",
    Config=Config,
    provides=[PROMPT_TEMPLATE_PROVIDER.key],
    requires=[],
    layer="L1",
    effects="none",
    description="Provide profile-selected prompt templates (built-ins + Profile overrides).",
    test_suite="tests/architecture/test_prompt_template_provider.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca-prompt-template-provider-builtin.checked",
                "lca-prompt-template-provider-builtin.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Provide the merged PromptTemplateProvider."""

    provider = _build_provider(config)
    ctx.provide(PROMPT_TEMPLATE_PROVIDER.key, provider)


__all__ = ["Config", "_ProviderImpl", "setup"]
