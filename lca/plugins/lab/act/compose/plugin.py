"""act.compose — capability refs → BodyHandle(scope-bound).

worker: compose(*, plan_ref, body_ref, tool_registry_ref, safe_executor_ref, transport_ref) -> body_handle
kind: TRANSFORMER
out_port: body_handle
config: plan_ref body_ref tool_registry_ref safe_executor_ref transport_ref
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BodyHandle:
    """act.execute 拿到的 typed handle;由 act.compose 节点化装配。

    Worker 不感知 framework 句柄;framework 在 setup 时按 ref 装配 SimpleBody,
    Worker 只持 typed ref。
    """

    body_ref: str
    tool_registry_ref: str
    safe_executor_ref: str
    transport_ref: str
    plan_ref: str

    def act(self, *, decision: object) -> object:
        """纯协议转发:framework 在调用时根据 refs 装配 SimpleBody。"""
        return {"decision": decision, "body_ref": self.body_ref, "plan_ref": self.plan_ref}


def compose(
    *,
    plan_ref: str,
    body_ref: str = "lab.body",
    tool_registry_ref: str = "lab.tool_registry",
    safe_executor_ref: str = "lab.safe_executor",
    transport_ref: str = "lab.transport",
) -> BodyHandle:
    """按 capability refs 组装 typed BodyHandle(只装配,不执行)。"""
    return BodyHandle(
        body_ref=body_ref,
        tool_registry_ref=tool_registry_ref,
        safe_executor_ref=safe_executor_ref,
        transport_ref=transport_ref,
        plan_ref=plan_ref,
    )


__all__ = ["BodyHandle", "compose"]
