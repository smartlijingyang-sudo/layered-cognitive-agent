# act.authorize — Intent → stamped Intent(verdict)。
#
# 做什么:按 effect_kind + tool 白名单决定 verdict (allow/deny/skip),写回 Intent。
# 不做什么:不调 Body、不调框架、不发请求。
#
# ADR-0211 §1.1:execute keyword-only / typed。
# ADR-0211 §5.2:Config 只放静态值(allow 白名单);不放端口名。
# ADR-0211 §5.3:一个 Worker 一个动词 —— authorize 只做"裁决"。
#
# delete-when:无。

from __future__ import annotations

from dataclasses import replace

from lca.plugins.lab.act.shape.plugin import Intent
from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier


# ---------------------------------------------------------------------------
# Carrier
# ---------------------------------------------------------------------------
_CARRIER = LabCarrier(
    id="lab.act.authorize",
    stage="act",
    kind="TRANSFORMER",
    description="act.authorize — Intent → stamped Intent with grant verdict.",
    node_id="authorize",
    source_module="lca.plugins.lab.act.authorize.plugin",
    source_class="authorize",
    provides=("lab.act.authorize.out:authorized",),
    requires=("lab.act.shape.out:intent",),
    emits=("lab.act.authorize.out:authorized",),
    inputs=(("intent", "intent", True),),
    outputs=(("authorized", "intent"),),
    out_capabilities=("lab.act.authorize.out:authorized",),
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


# ---------------------------------------------------------------------------
# Verdict 闭集
# ---------------------------------------------------------------------------

# ADR-0211 §3:verdict / effect_kind 闭集,放模块顶部让 lint 易检。
VERDICT_ALLOW = "allow"
VERDICT_DENY = "deny"
VERDICT_SKIP = "skip"

# effect_kind → 默认 verdict;no_effect / 未识别 → skip;无 tool 调用 → allow。
EFFECT_KIND_NO_TOOL_VERDICT = frozenset(
    {"respond", "stop", "ask_human", "delegate", "handoff"}
)
EFFECT_KIND_REQUIRES_TOOL = frozenset({"use_tool", "call_tool"})


def authorize(*, intent: Intent, allow: frozenset[str]) -> Intent:
    """按 effect_kind + tool 白名单,给 Intent 打 verdict。"""
    if intent.effect_kind == "no_effect":
        return replace(intent, verdict=VERDICT_SKIP)
    if intent.effect_kind in EFFECT_KIND_NO_TOOL_VERDICT:
        return replace(intent, verdict=VERDICT_ALLOW)
    if intent.effect_kind in EFFECT_KIND_REQUIRES_TOOL:
        verdict = VERDICT_ALLOW if intent.tool in allow else VERDICT_DENY
        return replace(intent, verdict=verdict)
    return replace(intent, verdict=VERDICT_SKIP)


__all__ = [
    "EFFECT_KIND_NO_TOOL_VERDICT",
    "EFFECT_KIND_REQUIRES_TOOL",
    "VERDICT_ALLOW",
    "VERDICT_DENY",
    "VERDICT_SKIP",
    "authorize",
    "setup",
]
