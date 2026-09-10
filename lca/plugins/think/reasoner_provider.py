"""phase.think.reasoner — PromptReasoner instance provider for inner think subgraph.

构造 :class:`PromptReasoner` 单例并注册到 ``reasoner`` capability 键。
think 子图三个 reason 节点(``plan`` / ``render`` / ``complete``)通过
``context.runtime.reasoner`` 读这个实例,duck-typed 调
``build_turn_plan`` / ``render_turn`` / ``complete_turn``。

LLM 凭证与 adapter 装配由 ``ProductionLLMResolver`` 在 framework
层完成,本 plugin 直接从 Bundle ``config.default_model`` 走 profile
配置装配 adapter。``llm_resolver`` capability seam 已被本仓库的
think-subgraph 迁移退役,不要在本插件上重新声明这条 requires。

``RoleProfile`` 由上游 ``phase.think.role_profile`` provider 通过
``reasoner.role_profile`` capability 注入,本 plugin 不再持有默认字面量。
没有上游 provider 时 boot 会因 ``UndeclaredInteractionError`` /
``MissingCapabilityError`` 失败,而不是悄悄把 ``assistant`` 身份
写进 LLM prompt。

与 ``lca.plugins.reasoner.prompt`` 的关系(同名 seam 不同形态):

- ``reasoner.prompt``(:class:`PromptReasoner` **class**):外层
  :class:`SimpleBrainFactory` 用 ``reasoner_cls=`` per-call 实例化。
- 本 plugin(``reasoner``,**instance**):内层 think subgraph 跨节点复用,
  LLMAdapter / RoleProfile 在 boot 时绑一次。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import REASONER_ROLE_PROFILE
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.team.role.team import RoleProfile
from lca.contracts.protocols import Reasoner
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.llm.resolver import ProductionLLMResolver


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_model: str | None = None


@plugin(
    id="phase.think.reasoner",
    provides=("reasoner",),
    requires=(REASONER_ROLE_PROFILE.key,),
    implements=[Reasoner],
    layer="L1",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Provide a configured PromptReasoner instance for the inner "
        "think subgraph. Built from the active LLMResolver adapter."
    ),
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G5_COGNITION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_reasoner.checked",
                "phase_think_reasoner.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("reasoner.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Resolve LLM adapter and bind it to PromptReasoner; register ``reasoner`` capability."""
    from lca.cognition.brain.reasoner.reasoner import PromptReasoner
    from lca.infrastructure.llm.config import llm_credentials

    # ``ProductionLLMResolver`` 不自己读 env:``llm_credentials()`` 把 ``.env`` 里的
    # ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL`` 经由 pydantic-settings
    # 抬到 process env 之后取出来(BOOTSTRAP 白名单包含 ``LLM_`` 前缀)。
    api_key, base_url, model_from_env = llm_credentials()
    adapter = ProductionLLMResolver(
        api_key=api_key,
        base_url=base_url,
        default_model=config.default_model or model_from_env,
    ).resolve()
    role_profile = ctx.require(REASONER_ROLE_PROFILE.key)
    if not isinstance(role_profile, RoleProfile):
        raise TypeError(
            "reasoner.role_profile must be a RoleProfile instance, got "
            f"{type(role_profile).__name__}"
        )
    # Capture the boot-time ToolsService so the reasoner can fork a
    # per-run tool list inside ``complete_turn`` (``fork_for_run``
    # binds the registered factories against the run dict). Walk past
    # the audited facade (``ctx.require`` enforces the manifest
    # ``requires=`` and would fail here) and read from the cordis
    # Context directly.
    tools_service: object | None = None
    runtime = getattr(ctx, "_runtime", None)
    if callable(runtime):
        try:
            tools_service = runtime().inject("tools")
        except Exception:
            tools_service = None
    reasoner = PromptReasoner(llm=adapter, role_profile=role_profile)
    reasoner._tools_service = tools_service  # type: ignore[attr-defined]
    ctx.provide("reasoner", reasoner)


__all__ = ["Config", "setup"]
