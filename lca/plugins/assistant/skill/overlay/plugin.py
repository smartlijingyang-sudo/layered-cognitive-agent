"""assistant.skill_overlay plugin manifest 与 boot。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import ASSISTANT_CATALOG, ASSISTANT_SKILL_OVERLAY
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_SKILL_ACTIVATED,
    ASSISTANT_SKILL_INSTALLED,
)
from lca.contracts.protocols.assistant.catalog import AssistantCatalog
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import EffectClass, PluginContext, PluginKind, plugin
from lca.plugins.assistant.events._events import emit_fact_event
from lca.plugins.assistant.skill.overlay.overlay import _AssistantSkillOverlayImpl


class Config(BaseModel):
    """无配置字段:home 路径经 ``assistant.catalog`` 解析,根路径由
    Catalog 的 Profile 注入拥有;本插件不读 ``os.environ``。"""

    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca.plugins.assistant.skill.overlay",
    provides=(ASSISTANT_SKILL_OVERLAY.key,),
    requires=(ASSISTANT_CATALOG.key, "event.bus"),
    layer="L4",
    kind=PluginKind.PROVIDER,
    # capability_plan_resolver 禁止多 effect class;网络拉取是 0048
    # SkillImporter 的 effect 面,本插件自身的持久副作用 = Home skills 写。
    effects=(EffectClass.FILESYSTEM,),
    description=(
        "助理域 skill 安装/激活(ADR-0187 §7 PR-6):0048 拉取 + 0067 三闸,"
        "只写本助理 Home 的 skills 子树,禁写全局 skills store;"
        "未验证包不可 activate。"
    ),
    test_suite="tests/plugins/assistant/test_skill_overlay.py",
    functional_group=FunctionalGroup.G10_COMPOSITION,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "lca.plugins.assistant.skill_overlay.checked",
                "lca.plugins.assistant.skill_overlay.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=(ASSISTANT_CATALOG.key, "event.bus"),
        emits=(ASSISTANT_SKILL_INSTALLED, ASSISTANT_SKILL_ACTIVATED),
        state_mutation="scoped",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """assistant.skill_overlay plugin boot。

    行为契约:

    1. ``ctx.require(assistant.catalog)`` 取 Catalog(先决依赖;DAG 保证
       catalog 先 boot);isinstance 校验 fail-loud。
    2. EP 发射走 audited ``ctx.emit``;``assistant.*`` EP 描述符由
       catalog plugin boot 期统一补登(12 个),本插件不重复注册。
    3. 拉取器默认 ``_default_url_importer``(0048 HttpSkillImporter 绑定
       Home 内 staging store);测试可经实现类构造参数替换。
    4. 全局技能库读缝默认 ``_default_global_store``,只被 ``relink_global_skills``
       读取(ADR-0243 D1);不是 capability,故不进 ``ownership.reads``,写路径
       仍 ⊆ ``{home}/skills/``。测试可经实现类构造参数替换。
    """
    del config
    catalog = ctx.require(ASSISTANT_CATALOG.key)
    if not isinstance(catalog, AssistantCatalog):
        raise TypeError(
            f"assistant.skill_overlay requires {ASSISTANT_CATALOG.key} 为 AssistantCatalog, "
            f"得到 {type(catalog).__name__}"
        )


    overlay = _AssistantSkillOverlayImpl(catalog=catalog, event_emitter=emit_fact_event)
    ctx.provide(ASSISTANT_SKILL_OVERLAY.key, overlay)
