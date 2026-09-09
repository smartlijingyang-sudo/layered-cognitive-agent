# act.shape — Decision → Intent。
#
# 做什么:把 Decision 重排成 act-phase Intent schema。
# 不做什么:不算 verdict、不调框架、不产出 Observation。
#
# ADR-0211 §1.1 W-1/W-2/W-3:execute keyword-only / typed / 无 framework ctx。
# ADR-0211 §5.1:签名 = 真实依赖,读者一眼看清。
# ADR-0211 §5.3:一个 Worker 一个动词 —— shape 只做"整形"。
#
# delete-when:无。

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.execution.decision import Decision
from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier


# ---------------------------------------------------------------------------
# Carrier —— framework 注册 marker。
# ---------------------------------------------------------------------------
_CARRIER = LabCarrier(
    id="lab.act.shape",
    stage="act",
    kind="TRANSFORMER",
    description="act.shape — Decision → Intent.",
    node_id="shape",
    source_module="lca.plugins.lab.act.shape.plugin",
    source_class="shape",
    provides=("lab.act.shape.out:intent",),
    requires=("decision",),
    emits=("lab.act.shape.out:intent",),
    inputs=(("decision", "decision", True),),
    outputs=(("intent", "intent"),),
    out_capabilities=("lab.act.shape.out:intent",),
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


# ---------------------------------------------------------------------------
# Typed worker —— 纯函数,5 行。
# ---------------------------------------------------------------------------

# ADR-0211 §3:effect_kind 闭集,放模块顶部让 lint 易检。
EFFECT_KIND_DEFAULT = "use_tool"


@dataclass(frozen=True, slots=True)
class Intent:
    """act-phase Intent:action_type + tool + args + effect_kind + verdict。"""

    action_type: str
    tool: str | None
    args: dict[str, Any]
    effect_kind: str
    verdict: str = "allow"


def shape(*, decision: Decision) -> Intent:
    """把 Decision 字典重排成 Intent。"""
    first_call = decision.tool_calls[0] if decision.tool_calls else None
    return Intent(
        action_type=decision.action_type,
        tool=first_call.tool_name if first_call else None,
        args=dict(first_call.arguments) if first_call else {},
        effect_kind=decision.extra.get("effect_kind", EFFECT_KIND_DEFAULT),
    )


__all__ = ["EFFECT_KIND_DEFAULT", "Intent", "setup", "shape"]
