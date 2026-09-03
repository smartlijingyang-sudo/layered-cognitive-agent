"""Langfuse evaluation scorer factory plugin (Tier-2).

把 Langfuse 打分函数注册为 ``fact_scorers`` 的 factory。Langfuse SDK 懒加载：
构造期不校验、调用期才创建客户端；失败不传播（评估是辅助通道）。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.observability.ports import ScorerFn
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin(
    id="lca-langfuse-eval-scorer",
    requires=["fact_scorers"],
    implements=[ScorerFn],
    layer="L0",
    effects="network",
    description="Register Langfuse scorer factory as fact_scorers['langfuse'].",
    test_suite="tests/test_observability_scorer.py::test_langfuse_scorer_registered",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G10_COMPOSITION, control_slots=(ControlSlot.OBSERVE_WILDCARD,)
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-langfuse-eval-scorer.checked", "lca-langfuse-eval-scorer.served")
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
    from lca.infrastructure.observability import NamedRegistry, ObservabilitySettings

    registry: NamedRegistry = ctx.require("fact_scorers")

    def _make_langfuse(settings: ObservabilitySettings | None = None, **_: Any) -> ScorerFn:
        cfg = settings or ObservabilitySettings()

        def _score_current(name: str, value: float, attributes: dict[str, Any]) -> None:
            """向 Langfuse SDK 转发分数。SDK 未安装或失败时降级为 no-op。"""
            try:
                import langfuse  # noqa: F401  # 验证依赖
                from langfuse import Langfuse

                client = Langfuse(
                    public_key=cfg.langfuse_public_key,
                    secret_key=cfg.langfuse_secret_key,
                    host=cfg.langfuse_host,
                )
                client.score_current_span(name=name, value=value, data=attributes or None)
            except ImportError:
                pass  # INTENTIONAL: Langfuse SDK 未安装；不影响框架
            except Exception:
                # INTENTIONAL: 评估通道是 best-effort 辅助,失败不传播;
                # 不阻断主评分路径(LCA 内置 fact_scorer 仍跑)。
                return

        return _score_current

    registry.register("langfuse", _make_langfuse)
