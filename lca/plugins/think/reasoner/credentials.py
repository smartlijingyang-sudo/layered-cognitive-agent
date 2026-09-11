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
    import logging
    import os

    from lca.infrastructure.llm.config import llm_credentials
    from lca.infrastructure.llm.resolver import ProductionLLMResolver

    _log = logging.getLogger(__name__)
    api_key, base_url, model_from_env = llm_credentials()
    env_api_key = os.environ.get("LLM_API_KEY")
    env_base_url = os.environ.get("LLM_BASE_URL")
    env_model = os.environ.get("LLM_MODEL")
    env_api_style = os.environ.get("LLM_API_STYLE")
    key_loaded = bool(api_key)
    _log.info(
        "phase.think.reasoner.credentials checked: "
        "resolved.api_key.present=%s env.LLM_API_KEY.present=%s "
        "env.LLM_BASE_URL=%s env.LLM_MODEL=%s env.LLM_API_STYLE=%s",
        key_loaded,
        bool(env_api_key),
        env_base_url,
        env_model,
        env_api_style,
    )
    ctx.emit(
        "phase_think_reasoner_credentials.checked",
        {
            "llm_api_key_present": key_loaded,
            "env_llm_api_key_present": bool(env_api_key),
            "env_llm_base_url": env_base_url,
            "env_llm_model": env_model,
            "env_llm_api_style": env_api_style,
            "resolved_base_url": base_url,
            "resolved_model": model_from_env,
        },
    )
    if not key_loaded:
        raise RuntimeError(
            "phase.think.reasoner.credentials: LLM_API_KEY 未配置。"
            f" env.LLM_API_KEY present={bool(env_api_key)},"
            f" .env 加载后 llm_credentials().api_key 为空。"
            " 检查 cwd 下是否存在 .env 或 BOOTSTRAP_PREFIXES 是否含 LLM_。"
        )
    adapter = ProductionLLMResolver(
        api_key=api_key,
        base_url=base_url,
        default_model=config.default_model or model_from_env,
    ).resolve()
    _log.info(
        "phase.think.reasoner.credentials served: adapter_type=%s",
        type(adapter).__name__,
    )
    ctx.emit(
        "phase_think_reasoner_credentials.served",
        {
            "adapter_type": type(adapter).__name__,
            "adapter_model": getattr(adapter, "_model", None) or getattr(adapter, "model", None),
            "adapter_base_url": getattr(adapter, "_base_url", None) or getattr(adapter, "base_url", None),
            "adapter_api_style": str(getattr(adapter, "_api", None) or getattr(adapter, "api", None)),
        },
    )
    ctx.provide("llm_adapter", adapter)


__all__ = ["Config", "setup"]
