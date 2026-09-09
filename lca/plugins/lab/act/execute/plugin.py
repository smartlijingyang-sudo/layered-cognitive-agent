# act.execute — Intent + BodyHandle → Observation(world 效应唯一出口)。
#
# 做什么:对一次授权 Intent 调一次 BodyHandle。
# 不做什么:不装配(由 act.compose 节点化)、不处理异常(framework 按 on_error
# 处理,违反 ADR-0211 §1.1 W-7/W-8)、不写 receipt、不调其它 worker。
#
# ADR-0211 §1.1 W-1/W-2/W-3:execute keyword-only / typed / 无 framework ctx。
# ADR-0211 §5.3:一个 Worker 一个动词 —— execute 只做"执行"。
#
# delete-when:无。

from __future__ import annotations

from lca.contracts.models.core.execution.decision import Observation
from lca.plugins.lab.act.compose.plugin import BodyHandle
from lca.plugins.lab.act.shape.plugin import Intent
from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier


# ---------------------------------------------------------------------------
# Carrier
# ---------------------------------------------------------------------------
_CARRIER = LabCarrier(
    id="lab.act.execute",
    stage="act",
    kind="EXECUTOR",
    description="act.execute — BodyHandle + Intent → Observation.",
    node_id="execute",
    source_module="lca.plugins.lab.act.execute.plugin",
    source_class="execute",
    provides=("lab.act.execute.out:observation",),
    requires=(
        "lab.act.authorize.out:authorized",
        "lab.act.compose.out:body_handle",
        "lab.body",
    ),
    emits=("lab.act.execute.out:observation",),
    inputs=(("authorized", "intent", True), ("body_handle", "body_handle", True)),
    outputs=(("observation", "observation"),),
    out_capabilities=("lab.act.execute.out:observation",),
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


# ---------------------------------------------------------------------------
# Typed worker —— 纯协议调用,3 行。
# ---------------------------------------------------------------------------


def execute(*, intent: Intent, body: BodyHandle) -> Observation:
    """调一次 BodyHandle.act(decision=intent) → Observation。

    异常自然冒到 framework,framework 按 Config.on_error 处理
    (fail/retry/route);Worker 不写 try/except,违反 ADR-0211 §1.1 W-7。
    """
    return body.act(decision=intent)


__all__ = ["execute", "setup"]
