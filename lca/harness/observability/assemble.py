"""assemble_observability —— boot 阶段唯一装配函数。

解析 settings + 插件注册表 → 实例化各 backend → 组成 BoundObservability →
挂到 plugin ctx 上。业务代码通过 facade 函数（record/span/annotate/score）
间接访问。

装配后所有 backend 引用冻结；运行期只通过 facade 修改 RunContext（scope
metadata），不修改 backend 实例。Backends 本身通过 plugin ctx 注入。

不返回任何"hub"——只 ctx.provide 各组件，boot 阶段通过 invoke 消费。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.observability.named_registry import NamedRegistry
from lca.contracts.observability.ports import (
    AttributePolicyBackend,
    JournalBackend,
    ScorerFn,
    TracerBackend,
)
from lca.layer0_infra.observability import (
    AttributePolicy,
    ObservabilitySettings,
)
from lca.layer0_infra.observability.facade import BoundObservability

if TYPE_CHECKING:
    from lca.harness.plugin_api import PluginContext


def assemble_observability(
    ctx: Any,
    settings: ObservabilitySettings | None = None,
) -> BoundObservability:
    """从注册表 + settings 装配 BoundObservability 并挂到 ctx。

    装配顺序：
    1. attribute_policy（policy 是其它组件的前置）
    2. fact_readers（多个并存，扇出到 journal）
    3. journal_backend（接收 policy + readers）
    4. tracer_backend
    5. fact_scorers（多个并存）
    6. 组装 BoundObservability(journal, tracer, policy, scorers)

    任何 seam 缺失则跳过对应组件；运行时由 facade 安全 no-op。

    ``ctx`` 接受 cordis ``Context`` 或 ``PluginContext`` 协议；缺失键通过
    ``inject(..., default=None)`` 跳过，避免依赖 ``has()`` 公共方法。
    """
    cfg = settings or ObservabilitySettings()

    def _maybe(key: str) -> Any:
        inject = getattr(ctx, "inject", None)
        if not callable(inject):
            return None
        try:
            return ctx.inject(key, default=None)
        except (KeyError, TypeError):
            return None

    # 1. policy
    policy: AttributePolicyBackend | None = None
    policy_registry = _maybe("attribute_policy_backends")
    if isinstance(policy_registry, NamedRegistry) and "default" in policy_registry:
        policy = policy_registry.get("default")(cfg)

    # 2. readers
    readers: list[Any] = []
    reader_registry = _maybe("fact_readers")
    if isinstance(reader_registry, NamedRegistry):
        for name in cfg.reader_backends():
            if name in reader_registry:
                factory = reader_registry.get(name)
                readers.append(factory(cfg))

    # 3. journal
    journal: JournalBackend | None = None
    journal_registry = _maybe("journal_backends")
    if isinstance(journal_registry, NamedRegistry):
        backend_name = cfg.journal_backend
        if backend_name in journal_registry:
            factory = journal_registry.get(backend_name)
            # 工厂签名：(settings, projections=..., policy=...)
            journal = factory(cfg, projections=tuple(readers), policy=policy)

    # 4. tracer
    tracer: TracerBackend | None = None
    tracer_registry = _maybe("tracer_backends")
    if isinstance(tracer_registry, NamedRegistry):
        backend_name = cfg.tracer_backend
        if backend_name in tracer_registry:
            factory = tracer_registry.get(backend_name)
            tracer = factory(cfg, policy=policy)

    # 5. scorers
    scorers: list[ScorerFn] = []
    scorer_registry = _maybe("fact_scorers")
    if isinstance(scorer_registry, NamedRegistry):
        for name in cfg.scorer_backends():
            if name in scorer_registry:
                factory = scorer_registry.get(name)
                scorers.append(factory(cfg))

    bound = BoundObservability(
        journal=journal,
        tracer=tracer,
        policy=policy,
        scorers=tuple(scorers),
    )
    provide = getattr(ctx, "provide", None)
    if callable(provide):
        provide("observability", bound)
    return bound


# 反向：创建未绑定 BoundObservability（测试/CLI 直接构造路径）
def make_minimal_bound(
    *,
    journal: JournalBackend | None = None,
    tracer: TracerBackend | None = None,
    policy: AttributePolicyBackend | None = None,
    scorers: tuple[ScorerFn, ...] = (),
) -> BoundObservability:
    """测试/CLI 直接构造 BoundObservability（不走 boot 路径）。"""
    return BoundObservability(
        journal=journal,
        tracer=tracer,
        policy=policy,
        scorers=scorers,
    )


# 默认 AttributePolicy：policy 注册表为空时 fallback
def default_policy() -> AttributePolicyBackend:
    """框架默认 attribute policy（标准 verbosity + 脱敏）。"""
    return AttributePolicy()


__all__ = ["assemble_observability", "default_policy", "make_minimal_bound"]
