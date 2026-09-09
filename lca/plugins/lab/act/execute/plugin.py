"""act.execute — Intent + BodyHandle → Observation(world 效应唯一出口).

worker: execute(*, intent, body) -> Observation
kind: EXECUTOR
out_port: observation
in: authorized=intent body_handle=body
"""
from agent_lab.primitives.artifact import Artifact

from lca.plugins.lab.act.compose.plugin import BodyHandle


def execute(*, intent: Artifact | None, body: Artifact | None) -> Artifact:
    """调一次 BodyHandle.act(decision=intent) → Observation。

    异常自然冒到 framework,framework 按 Config.on_error 处理
    (fail/retry/route);Worker 不写 try/except。

    在 demo 路径下,BodyHandle 是 typed handle;framework 在调用时
    根据 body_handle ref 装配 SimpleBody 并 invoke。返回的 Observation
    由 typed protocol 派生(此处给个占位 Artifact,真实执行由 framework 接 body)。
    """
    return Artifact(
        kind="text",
        content={
            "decision_id": intent.content.get("decision_id", "") if intent else "",
            "tool": (intent.content.get("tool") if intent else None),
            "executed_via": "lab_act_demo",
            "body_ref": body.content.get("body_ref", "lab.body") if body else "lab.body",
        },
    )


__all__ = ["execute"]
