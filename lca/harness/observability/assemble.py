"""assemble_observability —— boot 阶段唯一装配函数。

解析 settings + 插件注册表 → 实例化各 backend → 组成 BoundObservability →
挂到 plugin ctx 上。业务代码通过 facade 函数（record/span/annotate/score）
间接访问。

装配后所有 backend 引用冻结；运行期只通过 facade 修改 RunContext（scope
metadata），不修改 backend 实例。Backends 本身通过 plugin ctx 注入。

不返回任何"hub"——只 ctx.provide 各组件，boot 阶段通过 invoke 消费。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.named_registry import NamedRegistry
from lca.contracts.observability.ports import (
    AttributePolicyBackend,
    JournalBackend,
    ScorerFn,
    TracerBackend,
)
from lca.infrastructure.observability import (
    AttributePolicy,
    ObservabilitySettings,
)
from lca.infrastructure.observability.facade import BoundObservability


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
        policy_factory = policy_registry.get("default")
        if policy_factory is not None:
            policy = policy_factory(cfg)

    # 2. readers
    readers: list[Any] = []
    reader_registry = _maybe("fact_readers")
    if isinstance(reader_registry, NamedRegistry):
        for name in cfg.reader_backend_names():
            factory = reader_registry.get(name)
            if factory is None:
                continue
            readers.append(factory(cfg))

    # 3. journal
    journal: JournalBackend | None = None
    journal_registry = _maybe("journal_backends")
    # ADR-0065 L4: boot 期把 cordis 注入的 EventDescriptorRegistry 透传给
    # journal factory（也由 providers/event_descriptor bootstrap 灌 49 个内置
    # descriptor）。RunStore._apply_policy 优先用它，避免模块 fallback。
    descriptor_registry = _maybe("event_descriptor_registry")
    if isinstance(journal_registry, NamedRegistry):
        backend_name = cfg.journal_backend
        if backend_name:
            factory = journal_registry.get(backend_name)
            if factory is not None:
                # 工厂签名：(settings, projections=..., policy=..., descriptor_registry=...)
                journal = factory(
                    cfg,
                    projections=tuple(readers),
                    policy=policy,
                    descriptor_registry=descriptor_registry,
                )

    # 4. tracer
    tracer: TracerBackend | None = None
    tracer_registry = _maybe("tracer_backends")
    if isinstance(tracer_registry, NamedRegistry):
        backend_name = cfg.tracer_backend
        if backend_name:
            factory = tracer_registry.get(backend_name)
            if factory is not None:
                tracer = factory(cfg, policy=policy)

    # 5. scorers
    scorers: list[ScorerFn] = []
    scorer_registry = _maybe("fact_scorers")
    if isinstance(scorer_registry, NamedRegistry):
        for name in cfg.scorer_backend_names():
            factory = scorer_registry.get(name)
            if factory is None:
                continue
            scorers.append(factory(cfg))

    bound = BoundObservability(
        journal=journal,
        tracer=tracer,
        policy=policy,
        scorers=tuple(scorers),
        evidence_store=_maybe("evidence_store"),
        evidence_policy=_maybe("evidence_policy"),
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
