"""AutoReview 工具包装器 — ADR-0248 工具执行 seam 的三态审查。

``concept.tool.fork`` 在 ``auto_review_mode != "off"`` 时，用本包装器包住
每 Run 工具集：``execute`` 前调用 ``AutoReviewGate.evaluate``，按判决：
- ``allow``：放行内层工具；
- ``block``：返回失败 Observation（严禁读取敏感系统凭据）；
- ``escalate``：返回携带指纹的失败 Observation，模型可自行走低风险等价路径
  （Adapt）；完整人审卡（grant_approval 指纹重放放行）是后续 HITL 增强，
  本包装器先把硬闸拦截落地；
- ``adapt``：改写 ``command`` 为低权限等价命令后执行。

包装器保持内层 ``Tool`` 协议表面（name/description/parameters/幂等/校验），
因此 SafeExecutor、权限清单、Journal 观测到的工具名与内层完全一致。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_EXECUTION
from lca.contracts.models.auto_review.models import AutoReviewAction, AutoReviewVerdict
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.protocols import Tool
from lca.infrastructure.auto_review.gate import AutoReviewGate


class AutoReviewWrappedTool(Tool):
    """包一层 AutoReviewGate 的 Tool 装饰器。"""

    def __init__(self, inner: Tool, gate: AutoReviewGate) -> None:
        self._inner = inner
        self._gate = gate

    # ── Tool 协议表面：完全委托内层 ─────────────────────────
    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def description(self) -> str:
        return self._inner.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._inner.parameters

    @property
    def is_idempotent(self) -> bool:
        return self._inner.is_idempotent

    @property
    def effect_kind(self) -> str:
        return getattr(self._inner, "effect_kind", "ephemeral")

    @property
    def default_timeout_s(self) -> int:
        return self._inner.default_timeout_s

    def validate(self, args: dict[str, Any]) -> str | None:
        return self._inner.validate(args)

    # ── 执行：先过 AutoReview 硬闸 ──────────────────────────
    async def execute(self, args: dict[str, Any]) -> Observation:
        verdict = self._gate.evaluate(self._inner.name, args)
        if verdict.action == AutoReviewAction.ALLOW:
            return await self._inner.execute(args)

        if verdict.action == AutoReviewAction.ADAPT and verdict.adapted_command:
            adapted_args = dict(args)
            if "command" in adapted_args:
                adapted_args["command"] = verdict.adapted_command
            obs = await self._inner.execute(adapted_args)
            obs.extra["auto_review_adapted"] = True
            return obs

        return self._denied(verdict)

    @staticmethod
    def _denied(verdict: AutoReviewVerdict) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=verdict.reason,
            extra={
                FAILURE_KIND: FAILURE_KIND_EXECUTION,
                "auto_review_action": verdict.action.value,
                "action_fingerprint": verdict.action_fingerprint or "",
                "auto_review_reason": verdict.reason,
            },
        )


__all__ = ["AutoReviewWrappedTool"]
