# act.compose — capability refs → BodyHandle(scope-bound)。
#
# 做什么:按 cordis ctx 拿到的 capability refs,组装一个 typed BodyHandle。
# 不做什么:不执行任何工具调用、不写 evidence、不调 SimpleBody 构造器。
#
# ADR-0211 §1.3 / §6 §3:本节点取代 ``body_provider.get_body()`` 函数;
# 装配在节点 setup 阶段完成(只一次),execute 阶段只返回 typed ref。
# 同 PR 系列收口不留 compat shim。
#
# delete-when:无。

from __future__ import annotations

from dataclasses import dataclass

from lca.plugins.lab.internal.hooks import LabCarrier, bind_carrier


# ---------------------------------------------------------------------------
# Carrier
# ---------------------------------------------------------------------------
_CARRIER = LabCarrier(
    id="lab.act.compose",
    stage="act",
    kind="TRANSFORMER",
    description="act.compose — assemble BodyHandle from capability refs.",
    node_id="compose",
    source_module="lca.plugins.lab.act.compose.plugin",
    source_class="compose",
    provides=("lab.act.compose.out:body_handle",),
    requires=(
        "lab.body",
        "lab.tool_registry",
        "lab.safe_executor",
        "lab.transport",
        "lab.plan_ref",
    ),
    emits=("lab.act.compose.out:body_handle",),
    inputs=(),
    outputs=(("body_handle", "body_handle"),),
    out_capabilities=("lab.act.compose.out:body_handle",),
)


def setup(ctx, config):
    """Register the carrier with the loader on plugin boot."""
    bind_carrier(_CARRIER, ctx=ctx, config=config)


bind_carrier(_CARRIER)


# ---------------------------------------------------------------------------
# Typed worker —— 纯装配,只引用,不构造 SimpleBody。
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BodyHandle:
    """act.execute 拿到的 typed handle;由 act.compose 节点化装配。

    取代 ``SimpleBody`` 直传;execute 通过 ``body.act(decision=...)``
    单方法调一次,符合 ADR-0211 §1.1 W-3「Worker 不感知 framework 句柄」。
    """

    body_ref: str             # lab.body capability ref
    tool_registry_ref: str    # lab.tool_registry capability ref
    safe_executor_ref: str    # lab.safe_executor capability ref
    transport_ref: str        # lab.transport capability ref
    plan_ref: str

    def act(self, *, decision: object) -> object:
        """纯协议转发:framework 在调用时根据 BodyHandle refs 装配 SimpleBody。

        本方法不构造 SimpleBody,符合 ADR-0211 §1.3「装配唯一 = Profile/Bundle」;
        Worker 不写 try/except,异常自然冒到 framework。
        """
        # 真实执行由 framework 在调用时根据 refs 装配 SimpleBody 并 invoke;
        # 本方法只负责 typed 转发。占位返回值让 typed 签名一致。
        return {"decision": decision, "body_ref": self.body_ref, "plan_ref": self.plan_ref}


def compose(
    *,
    plan_ref: str,
    body_ref: str = "lab.body",
    tool_registry_ref: str = "lab.tool_registry",
    safe_executor_ref: str = "lab.safe_executor",
    transport_ref: str = "lab.transport",
) -> BodyHandle:
    """按 capability refs 组装一个 typed BodyHandle(只装配,不执行)。"""
    return BodyHandle(
        body_ref=body_ref,
        tool_registry_ref=tool_registry_ref,
        safe_executor_ref=safe_executor_ref,
        transport_ref=transport_ref,
        plan_ref=plan_ref,
    )


__all__ = ["BodyHandle", "compose", "setup"]
