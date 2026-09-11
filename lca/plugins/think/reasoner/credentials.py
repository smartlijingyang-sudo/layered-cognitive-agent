"""phase.think.reasoner.credentials — resolve boot-time LLM adapter.

Reads ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL`` from process env
(via :func:`llm_credentials`, BOOTSTRAP-prefixed ``LLM_``) and produces a
configured :class:`LLMAdapter` through :class:`ProductionLLMResolver`.
The adapter is published as ``llm_adapter`` for the downstream
``phase.think.reasoner.compose`` plugin (and any other consumer that needs
a runtime LLM instance).

``llm_resolver`` capability seam 已被本仓库的 think-subgraph 迁移退役,
本 plugin 不重新声明这条 requires。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_model: str | None = None


@plugin(
    id="phase.think.reasoner.credentials",
    provides=("llm_adapter",),
    requires=(),
    layer="L1",
    effects="none",
    kind=PluginKind.PROVIDER,
    description=(
        "Resolve boot-time LLM adapter from LLM_* env via "
        "ProductionLLMResolver and publish as llm_adapter capability."
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
                "phase_think_reasoner_credentials.checked",
                "phase_think_reasoner_credentials.served",
            )
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("llm_adapter.checked",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Resolve LLM adapter and publish as ``llm_adapter`` capability."""
    from lca.infrastructure.llm.config import llm_credentials
    from lca.infrastructure.llm.resolver import ProductionLLMResolver

    # ``ProductionLLMResolver`` 不自己读 env:``llm_credentials()`` 把 ``.env`` 里的
    # ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL`` 经由 pydantic-settings
    # 抬到 process env 之后取出来(BOOTSTRAP 白名单包含 ``LLM_`` 前缀)。
    api_key, base_url, model_from_env = llm_credentials()
    adapter = ProductionLLMResolver(
        api_key=api_key,
        base_url=base_url,
        default_model=config.default_model or model_from_env,
    ).resolve()
    ctx.provide("llm_adapter", adapter)


__all__ = ["Config", "setup"]
