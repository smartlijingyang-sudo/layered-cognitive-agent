"""assistant.catalog plugin —— ADR-0187 §7 PR-3。

薄 Catalog 唯一实现:

- ``provides=("assistant.catalog",)``;
- ``create / get / list`` —— Home CRUD(PR-3 范围);
- ``revise_profile / reimport`` —— 配置面唯一写入口(ADR-0242 D6);
- ``retire`` —— COMPAT 占位(delete-when: 2026-12-31,待 retire 入口落地)。

实现已拆分为 ``catalog/`` 包内聚焦子模块:

- ``handlers`` —— ``_AssistantCatalogImpl`` 与 Home CRUD / 技能物化;
- ``soul`` / ``plan_overlay`` / ``manifest`` / ``events`` —— 校验与辅助;
- 本模块保持 ``lca.plugins.domain.assistant.catalog.plugin`` 作为插件入口,
  并 re-export 公共 API 供既有 importers 使用。

三层真值(ADR-0187 §3 D2):

| 面 | 字段 | 进 manifest digest? |
|---|---|---|
| 配置(SSOT) | profile / SOUL / USER / AGENTS / goals / grants / tools | 是 |
| 记忆 | MEMORY.md / memory/ | 否(I-A13) |
| 工作区 | workspace/ | 否 |

根路径仅经 Profile ``{from_env: LCA_ASSISTANTS_ROOT}`` 注入;**禁止**
本模块读 ``os.environ``。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_BOOTSTRAP_COMPLETED,
    ASSISTANT_CREATED,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.assistant.home._home_layout import (
    AssistantAlreadyExistsError,
    AssistantCatalogError,
    AssistantDigestMismatchError,
    SoulValidationError,
)

from .handlers import _AssistantCatalogImpl
from .plan_overlay import PlanOverlayValidationError

# ── Plugin 配置 ───────────────────────────────────────────────────────


class Config(BaseModel):
    """Plugin 配置:根路径仅来自 Profile 注入的 ``LCA_ASSISTANTS_ROOT``。

    ``assistants_root`` 字段是 Profile 装配期由 ``{from_env: LCA_ASSISTANTS_ROOT}``
    展开的实际值。profile 缺字段时 resolver 抛错而非 silent 默认(fail-loud)。
    """

    model_config = ConfigDict(extra="forbid")

    assistants_root: str = Field(min_length=1)
    """``{from_env: LCA_ASSISTANTS_ROOT}`` 展开后的根路径。"""


# ── Plugin manifest ───────────────────────────────────────────────────


@plugin(
    id="lca.plugins.assistant.catalog.catalog",
    provides=(ASSISTANT_CATALOG.key,),
    requires=("event.bus", "event_descriptor_registry"),
    layer="L4",
    kind=PluginKind.PROVIDER,
    effects=(EffectClass.FILESYSTEM,),
    description=(
        "Home CRUD + manifest digest 校验(ADR-0187 §7 PR-3);"
        "不做 install/evolve/job,详见 protocol AssistantCatalog 注释。"
    ),
    test_suite="tests/plugins/assistant/test_catalog.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca.plugins.assistant.catalog.checked",
                "lca.plugins.assistant.catalog.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("event.bus", "event_descriptor_registry"),
        emits=(ASSISTANT_CREATED, ASSISTANT_BOOTSTRAP_COMPLETED),
        state_mutation="scoped",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """assistant.catalog plugin boot。

    行为契约:

    1. 取 Profile 注入的 ``assistants_root``(由 ``{from_env: LCA_ASSISTANTS_ROOT}``
       展开),构造 :class:`_AssistantCatalogImpl`;**不**读 ``os.environ``。
    2. 若 ``event_descriptor_registry`` 已登记 ``assistant.*`` EP 描述符,
       跳过(避免重复 register);否则补登 12 个 assistant 描述符(PR-2
       已落 contracts 层冻结元数据,本步骤仅在 registry 缺位时补齐)。
    3. EP 发射走 audited ``ctx.emit``(PluginEventBus.emit),具体 EventBus.publish
       由 lca.events.bus plugin 装配期安装。

    失败语义:``assistants_root`` 不可写 → 立即抛 ProfileResolveError 衍生错误
    由 plugin manager 接住(不静默降级到默认路径)。
    """
    from lca.infrastructure.path import expand_user_path

    root = expand_user_path(config.assistants_root)

    def _emit(event: str, payload: Mapping[str, Any]) -> Any:
        from lca.infrastructure.observability.domain_event_publish import (
            publish_structural_event,
        )

        return publish_structural_event(
            execution_point=event,
            channel="fact",
            payload=dict(payload),
            producer=type(None),
        )

    from lca.infrastructure.skills.disk.store import DiskSkillPackageStore

    catalog = _AssistantCatalogImpl(
        root=root,
        event_emitter=_emit,
        role_resolver=_try_build_role_resolver(),
        global_skills_store=DiskSkillPackageStore(),
        user_store=ctx.soft_get("assistant.ownership"),
    )
    ctx.provide(ASSISTANT_CATALOG.key, catalog)

    # 补登 assistant EP 描述符:PR-2 已落 contracts 层 _ASSISTANT_EVENT_DESCRIPTORS;
    # 若 event_descriptor_registry 已被 lca-event-descriptor-bootstrap 灌入 12 个 EP,
    # 此处 register 会因同名已存在抛错 → 已存在则忽略。
    registry = ctx.soft_get("event_descriptor_registry")
    if registry is not None:
        from contextlib import suppress

        from lca.contracts.observability.closure.assistant_ep_closure import (
            all_assistant_event_descriptors,
        )

        for descriptor in all_assistant_event_descriptors():
            with suppress(ValueError):
                # 已登记(PR-2 bootstrap path);按 PR-2 闭集规则不动现有登记
                registry.register(descriptor, replace=False)


# 用于测试在不接 ctx 时直接构造
AssistantCatalogImpl = _AssistantCatalogImpl


def _try_build_role_resolver() -> Any | None:
    """尝试构造 FileRoleCardResolver；roles/ 不可用则返回 None（不阻断 catalog boot）。"""
    try:
        from lca.infrastructure.tools.assistant.role_card_resolver import FileRoleCardResolver

        return FileRoleCardResolver()
    except Exception:
        return None


__all__ = [
    "AssistantAlreadyExistsError",
    "AssistantCatalogError",
    "AssistantCatalogImpl",
    "AssistantDigestMismatchError",
    "Config",
    "PlanOverlayValidationError",
    "SoulValidationError",
    "setup",
]
