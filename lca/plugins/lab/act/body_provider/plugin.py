# act.body_provider — lab.body capability 的 marker provider。
#
# 做什么:声明 ``lab.body`` capability key 由本 provider 提供;在 boot 时
# 通过 Cordis ctx 装配 SimpleBody(由 ``compose`` 函数内部调)。
# 不做什么:不再 export ``get_body()`` 函数(由 act.compose 节点接管);
# 不再被 act.execute / body / dispatch 等 worker 文件 import(违反
# ADR-0211 §1.3「装配唯一 = Profile/Bundle」)。
#
# ADR-0211 §6 §3:本文件保留但收紧 — ``get_body()`` 函数退役;
# ``act.compose`` 节点化接管装配职责。

from __future__ import annotations

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier


# ---------------------------------------------------------------------------
# Carrier —— lab.body capability 的 marker。
# ---------------------------------------------------------------------------
_CARRIER = LabCarrier(
    id="lab.act.body_provider",
    stage="composition",
    kind="PROVIDER",
    description="lab.body provider — SimpleBody composition for act.compose.",
    node_id="body_provider",
    source_module="lca.plugins.lab.act.body_provider.plugin",
    source_class="body_provider",
    provides=("lab.body",),
    requires=(
        "lab.tool_registry",
        "lab.safe_executor",
        "lab.transport",
        "lab.plan_ref",
    ),
    emits=("lab.body",),
    inputs=(),
    outputs=(("body", "body"),),
    out_capabilities=("lab.body",),
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


__all__ = ["setup"]
