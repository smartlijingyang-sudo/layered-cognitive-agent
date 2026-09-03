"""Spine 壳类 payload（ADR-0181 D2）。

承载 spine EP 字符串 + caller payload dict + chain 字段，套进
:class:`EventMechanism` 发送。SPINE_EXECUTION_POINTS 是 76 EP 字符串闭集
（原 ADR-0165 / ADR-0165.1 EXECUTION_POINTS 迁移）；不是 enum，EP 跨 5 层
（transport / kernel / agent_loop / cognition / body / llm / runtime），
跨层 enum 违反架构不变量。
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, model_validator

from lca.contracts.event import Category, EventPayload, Plane

# 76 EP 字符串闭集（原 lca/infrastructure/observability/spine/manifest.py
# EXECUTION_POINTS；试点 PR 暂不全量迁移，PR-2 全量迁移并标旧 manifest.py
# 删-when）。
SPINE_EXECUTION_POINTS: tuple[str, ...] = (
    # Transport (ADR-0112)
    "transport.route.enter",
    "transport.route.exit",
    "transport.sse.publish",
    # Kernel lifecycle
    "kernel.boot.start",
    "kernel.boot.completed",
    "kernel.run.start",
    "kernel.run.stop",
    "kernel.run.cancelled",
    # Agent loop
    "agent_loop.iteration.start",
    "agent_loop.iteration.end",
    # Cognition
    "brain.perceive.start",
    "brain.perceive.end",
    "brain.think.start",
    "brain.think.end",
    "brain.gate.start",
    "brain.gate.end",
    "critic.eval.start",
    "critic.eval.end",
    "reasoner.reason.start",
    "reasoner.reason.end",
    "prompt_assembler.start",
    "prompt_assembler.end",
    "synthesizer.merge",
    "skill_router.route",
    # Body / LLM
    "tool.invoked",
    "tool.completed",
    "tool.denied",
    "tool.retry_progress",
    "tool.lifecycle_ended",
    "tool.abandoned_before_invoke",
    "llm.call_started",
    "llm.call_completed",
    "llm.stream_token",
    "llm.stream_stall",
    "llm.tool_call_resolved",
    "sandbox.output_delta",
    # Runtime / orchestration
    "phase.start",
    "phase.end",
    "phase.fold",
    "phase.act.fold",
    "runtime.observed",
    "exception.caught",
    "exception.finally",
    "exception.lifecycle_finally",
    "agent.spawn",
    "agent.iteration",
    "agent.final",
    # Team
    "team.casting.started",
    "team.casting.completed",
    "team.casting.failed",
    "team.delegation.issued",
    "team.delegation.completed",
    "team.delegation.cache_hit",
    "team.message.published",
    # Memory
    "memory.read",
    "memory.write",
    "memory.committed",
    "memory.compacted",
    # Perception
    "perception.context_manifested",
    "perception.merged",
    "perception.step_text_delta",
    "perception.reasoning_delta",
    "perception.reasoning_completed",
    "perception.run_activity",
    # Control
    "control.approval.requested",
    "control.approval.resolved",
    "control.run_paused",
    "control.run_resumed",
    "control.inbox_followup",
    "plugin.authored",
    "plugin.mounted",
    "plugin.mount_rejected",
    "plugin.unmounted",
    "plugin.inspected",
    "preset.published",
    # Boot
    "boot.profile_resolved",
    "boot.plugin_fiber_spawned",
    "boot.observability_assembled",
)


class SpineEventPayload(EventPayload):
    """spine 壳类 payload（ADR-0181 D2）。

    承载：
    - ``category``（pydantic 父类必填）：试点 = SPINE_COGNITION_BRAIN_PERCEIVE_START
    - ``execution_point``：SPINE_EXECUTION_POINTS 闭集中的字符串
    - ``channel``：原 EventRecord.channel（fact/control/error/diagnostic）
    - ``payload``：原 caller_payload（dict）
    - chain 字段（span_id / parent_span_id / sequence / epoch / prev_event_hash）：
      由 SpineContext 注入；spine_chain_sink 落盘前算 hash chain
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Category = Category.SPINE_COGNITION_BRAIN_PERCEIVE_START
    execution_point: str
    channel: str = "fact"
    payload: dict[str, Any] = Field(default_factory=dict)
    span_id: str | None = None
    parent_span_id: str | None = None
    sequence: int = 0
    epoch: int = 0
    prev_event_hash: str | None = None

    @model_validator(mode="after")
    def _validate_spine_fields(self) -> SpineEventPayload:
        if self.execution_point not in SPINE_EXECUTION_POINTS:
            raise ValueError(
                f"UnknownSpineExecutionPoint({self.execution_point!r}): "
                f"not in SPINE_EXECUTION_POINTS whitelist"
            )
        if self.channel not in ("fact", "control", "error", "diagnostic"):
            raise ValueError(
                f"UnknownSpineChannel({self.channel!r}): "
                f"must be one of fact/control/error/diagnostic"
            )
        if self.sequence < 0:
            raise ValueError(f"sequence must be >= 0, got {self.sequence}")
        if self.epoch < 0:
            raise ValueError(f"epoch must be >= 0, got {self.epoch}")
        return self

    @property
    def plane(self) -> Plane:
        return Plane.OBSERVABILITY


__all__ = ["SPINE_EXECUTION_POINTS", "SpineEventPayload"]
