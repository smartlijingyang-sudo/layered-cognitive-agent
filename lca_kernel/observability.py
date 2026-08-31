"""观测装配(K5):唯一 ``BoundObservability`` 装配点。

Public surface
--------------
- :func:`install_observability` —— 把各 seam registry 装配成
  :class:`~lca.infrastructure.observability.facade.facade.BoundObservability`
  并挂到 :class:`cordis.Context` 的 ``"observability"`` 键。

Why a dedicated module
----------------------
原来 :mod:`lca.harness.profile.boot` 同时持有 ``_install_observability`` +
``_dispose_context`` + ``_boot_plugin`` + ``attach_profile_boot_products``,
违反 ADR-0083 §2 "可观测是横切观察" 收敛。拆出后 boot.py 只剩 cordis
Context + Fiber 启动;观测走 :func:`install_observability` 单入口,
``lca-ops diagnose plugin-tree`` 等诊断工具也能复用。
"""

from __future__ import annotations

from typing import Any

from lca.harness.observability import assemble_observability
from lca.infrastructure.observability import (
    BoundObservability,
    ObservabilitySettings,
)


def install_observability(ctx: Any) -> BoundObservability:
    """唯一 ``BoundObservability`` 装配点。

    把各 seam registry(``attribute_policy_backends`` / ``journal_backends`` /
    ``tracer_backends`` / ``fact_scorers``)装配成 ``BoundObservability``,
    通过 ``ctx.provide("observability", bound)`` 暴露给所有 plugin。

    Returns
    -------
    BoundObservability
        已绑定到 ``ctx`` 的对象;调用方可继续在 ``RunContext`` 上记录事件,
        但不能修改 backend 实例(backend 引用由 cordis Context 持有)。

    Notes
    -----
    装配顺序由 :func:`lca.harness.observability.assemble_observability` 控制
    (policy → readers → journal → tracer → scorers);该顺序保证 policy 先于
    journal / tracer 注入,fact_scorers 最后注入(它们消费已注入的 journal)。
    """
    return assemble_observability(ctx, ObservabilitySettings())


__all__ = ["install_observability"]
