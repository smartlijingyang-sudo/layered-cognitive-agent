"""PromptTemplateProvider — Cordis plugin owning the template-collection seam."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
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
    SectionKind,
    SectionReference,
)
from lca.contracts.models.cognition.prompt_assembly import (
    PromptTemplateProvider as Protocol_,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# ── Built-in templates (DSH-style declarative defaults) ──────────────


def _builtin_section_refs() -> tuple[tuple[str, str, bool, str | None], ...]:
    """Plain tuples kept here so this module stays import-cheap.

    Each entry: ``(name, kind, optional, fallback)``.
    """

    return (
        # react_prompt (no-LLM-supplied team sections)。
        # ADR-0265 §7 目标顺序：B1–B8 带序单调——
        # role→backstory→goal→current_date→developer_timestamp→user_profile→home→
        # autonomous_presets→tools→cloud_sandbox→available_skills→activated_skills→
        # task→context→react_workflow→react_tool_usage_guidelines→memory_retrieval→
        # skill_duty→vocal_contract（尾段）→runtime_env。
        ("role", "pure", False, None),
        ("backstory", "pure", False, None),
        ("goal", "pure", False, None),
        ("current_date", "stateful", False, None),
        # ADR-0265 §7 D1 决议②：developer_timestamp 是"now"唯一可信来源
        # （ADR-0259 C1 不变量），不许为可选；移入 B3 时间锚点带（current_date 旁），
        # 不再尾置。可选变必需：registry 缺失该段时装配期 fail-fast（与
        # memory_retrieval 的 7391aae5a 同语义）；渲染为空仍按 strip_empty_fields 跳过。
        ("developer_timestamp", "pure", False, ""),
        ("tools", "stateful", False, None),
        ("cloud_sandbox", "stateful", False, None),
        ("available_skills", "pure", False, None),
        ("activated_skills", "stateful", False, None),
        ("task", "stateful", False, None),
        ("context", "stateful", False, None),
        # react template's static instruction blocks
        ("react_workflow", "pure", True, ""),
        ("react_tool_usage_guidelines", "pure", True, ""),
        ("connected_services", "pure", True, ""),
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

    def refs(sl: tuple[tuple[str, str, bool, str | None], ...]) -> tuple[SectionReference, ...]:
        return tuple(
            SectionReference(name=n, kind=cast("SectionKind", k), optional=o, fallback=f)
            for (n, k, o, f) in sl
        )

    react_section_count = 14  # ADR-0265 §7 + connected_services 静态段，react 基座 14 段
    # ADR-0265 §7：B4 组（user_profile/home/autonomous_presets）插在 B3 之后、
    # B5（tools…）之前。base 前 5 段为 B1–B3（role/backstory/goal/current_date/
    # developer_timestamp），B4 组拼在其后，再接 base 剩余的 B5–B7 段。
    b1_b3_count = 5
    routing_extra = 4  # teammates, assigned_roles, member_reports, routing_instructions
    hierarchical_extra = 4  # member_status, evidence_pack, hierarchical_instructions (+ extra)
    home_ref = (("home", "stateful", True, ""),)
    autonomous_presets_ref = (("autonomous_presets", "stateful", True, ""),)
    user_profile_ref = (("user_profile", "stateful", True, ""),)
    b4_refs = user_profile_ref + home_ref + autonomous_presets_ref
    runtime_env_ref = (("runtime_env", "pure", True, ""),)
    # developer_timestamp 已移入 B3（见 _builtin_section_refs），不再是尾段；
    # runtime_env 留 B8 环境尾注（ADR-0265 §7 D1 决议②）。
    # ADR-0265 §3 C3 / §7④：memory_retrieval 承载 ADR-0260 C2 检索义务决策树，
    # 不得为可选（"义务缺席"不许用可选+fallback "" 静默）。optional=False 后，
    # 若 registry 缺失该 section，装配期抛 MissingPromptSectionError（fail-fast）；
    # section 正常渲染为空仍按 strip_empty_fields 跳过（渲染路径行为不变）。
    memory_retrieval_ref = (("memory_retrieval", "stateful", False, ""),)
    skill_duty_ref = (("skill_duty", "stateful", True, ""),)
    # ADR-0248：gated 模式声带契约（非 gated 渲染为空，零侵入）。ADR-0265 §7
    # 把 vocal_contract 定为 B7 行为规则段、落在 skill_duty 之后（原在 base
    # 头部 current_date 之前，为 T1 倒置 vocal_contract(B7)->current_date(B3)）；
    # 可选语义不变。
    vocal_contract_ref = (("vocal_contract", "stateful", True, ""),)
    adr0255_tail = memory_retrieval_ref + skill_duty_ref + vocal_contract_ref + runtime_env_ref
    return {
        "react_prompt": _PromptTemplate(
            id="react_prompt",
            variant=_variant_for("react_prompt"),
            sections=refs(
                base[:b1_b3_count]
                + b4_refs
                + base[b1_b3_count:react_section_count]
                + adr0255_tail
            ),
        ),
        "routing_prompt": _PromptTemplate(
            id="routing_prompt",
            variant=_variant_for("routing_prompt"),
            sections=refs(
                base[:b1_b3_count]
                + b4_refs
                + base[b1_b3_count:react_section_count]
                + base[react_section_count : react_section_count + routing_extra]
                + adr0255_tail
            ),
        ),
        "hierarchical_prompt": _PromptTemplate(
            id="hierarchical_prompt",
            variant=_variant_for("hierarchical_prompt"),
            sections=refs(
                base[:b1_b3_count]
                + b4_refs
                + base[b1_b3_count:react_section_count]
                + base[
                    react_section_count + routing_extra : react_section_count
                    + routing_extra
                    + hierarchical_extra
                ]
                + adr0255_tail
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


# ADR-0265 §3 C1：B1 宪法层（身份与人格，永不后移）。C2 ① 禁止 profile
# 把新段插到 B1 之前——B1 成员是唯一不依赖带序解释、可判定的锚点。
_B1_SECTION_NAMES = frozenset({"role", "backstory"})


def _validate_profile_template(
    tpl_cfg: PromptTemplateConfig,
    builtins: Mapping[str, _PromptTemplate],
) -> None:
    """ADR-0265 §3 C2 扩展纪律：模板加载期 fail-fast。

    profile 模板整体替换同名 builtin 模板时校验三条：
    1. 已知段的相对顺序必须与 builtin 一致（不许把 B4/B7 的段移到 B5 之前
       等跨序——相对顺序基线即 builtin 自身）；
    2. optional 只许收紧（True→False），不许放松（False→True，如把 B3 段改为可选）；
    3. 新段不许出现在 B1（role/backstory）之前。

    诚实注记：以 builtin 相对顺序为基线——builtin 已按 ADR-0265 §7 目标顺序
    重排（B1–B8 带序单调，T1 转绿），基线与带序表一致；逐字照抄 builtin 的
    合法 profile 不会被误杀。optional 收紧/放松与 B1 前置禁令见上。
    """
    builtin = builtins.get(tpl_cfg.id)
    refs = list(tpl_cfg.sections)
    if builtin is not None:
        builtin_by_name = {r.name: r for r in builtin.sections}
        prof_known = [r.name for r in refs if r.name in builtin_by_name]
        builtin_known = [r.name for r in builtin.sections if r.name in set(prof_known)]
        if prof_known != builtin_known:
            raise ValueError(
                f"profile template {tpl_cfg.id!r} reorders known sections "
                f"(ADR-0265 §3 C2): profile order {prof_known} != "
                f"builtin order {builtin_known}"
            )
        for r in refs:
            b = builtin_by_name.get(r.name)
            if b is not None and not b.optional and r.optional:
                raise ValueError(
                    f"profile template {tpl_cfg.id!r}: section {r.name!r} must "
                    f"not be relaxed to optional (ADR-0265 §3 C2: B3 等段不许改为可选)"
                )
    known_names = {r.name for r in builtin.sections} if builtin is not None else set()
    for r in refs:
        if r.name in _B1_SECTION_NAMES:
            break
        if r.name not in known_names:
            raise ValueError(
                f"profile template {tpl_cfg.id!r}: new section {r.name!r} must "
                f"not precede the B1 constitution layer (ADR-0265 §3 C2 ①)"
            )


def _build_provider(config: Config) -> _ProviderImpl:
    """Compose built-ins + profile overrides into the runtime provider."""

    builtins = _builtin_templates()
    merged: dict[str, _PromptTemplate] = dict(builtins)
    for tpl_cfg in config.profile_templates:
        _validate_profile_template(tpl_cfg, builtins)
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
    test_suite="tests/architecture/test_reasoner_template_catalog_capability.py::test_builtin_provider_has_the_complete_standard_template_set",
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
