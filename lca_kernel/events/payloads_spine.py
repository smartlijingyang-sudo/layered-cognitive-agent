"""Spine 壳类 payload（ADR-0181 D2 / ADR-0183 PR-7）。

承载 spine EP 字符串 + caller payload dict + chain 字段，套进
:class:`EventBus` 发送。SPINE_EXECUTION_POINTS 是 spine EP 字符串闭集，
完整迁移自 ``lca/infrastructure/observability/spine/manifest.py`` 的
``EXECUTION_POINTS`` 75 EP（试点 PR 已迁 1 个，余 74 个按 ADR-0181 §迁移
PR 切分逐个扩到 ``lca_kernel/events/config/observability/spine.yaml``）。

不是 enum，EP 跨 5 层（transport / kernel / agent_loop / cognition /
body / llm / runtime / writable / phase / step），跨层 enum 违反架构不变量。
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field, model_validator

from lca.contracts.event import Category, EventPayload, Plane

# spine EP 字符串闭集（原 lca/infrastructure/observability/spine/manifest.py
# EXECUTION_POINTS 75 EP 完整迁移；试点 PR 已迁 1 个 = brain.perceive.start）。
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
    "prompt_assembler.assemble.start",
    "prompt_assembler.assemble.end",
    "synthesizer.merge",
    "skill_router.route",
    "memory.read",
    "memory.write",
    # Body
    "body.tool.execute.start",
    "body.tool.execute.end",
    "body.tool.retry",
    # Writable matrix (ADR-0167 D11)
    "writable.step.start",
    "writable.step.end",
    "writable.segment.start",
    "writable.segment.end",
    # Loop cursor control (ADR-0169)
    "writable.iteration.halt",
    "writable.iteration.closing",
    "writable.iteration.close",
    "loop.fork",
    # Agent (PR-4)
    "agent.spawn",
    "agent.iteration",
    "agent.final",
    # Writable matrix phase events
    "perceive.phase.fold",
    "phase.perceive.fold",
    "phase.think.fold",
    "phase.gate.fold",
    "phase.remember.fold",
    "phase.stop.fold",
    "phase.reflect.fold",
    "phase.act.fold.start",
    "phase.act.fold.end",
    "phase.act.fold",
    "phase.tool.call.start",
    "phase.tool.call.end",
    "phase.tool.denied",
    # Lifecycle normalization (ADR-0166 S5)
    "lifecycle.finally",
    "body.sandbox.enter",
    "body.sandbox.exit",
    # LLM
    "llm.call.start",
    "llm.call.end",
    "llm.stream.token",
    "llm.stream.stall",
    "llm.request.header",
    # Runtime
    "runtime.reducer.apply",
    "runtime.checkpoint.create",
    "runtime.resume.start",
    "runtime.resume.end",
    "runtime.event_publisher.publish",
    # Phase graph
    "phase_graph.node.start",
    "phase_graph.node.end",
    "phase_graph.edge.transit",
    # Exception/finally
    "exception.caught",
    "exception.finally",
    # Coordinator record_* EP(ADR-0167 D2)
    "step.thinking.record",
    "step.tool_call.record",
    "step.tool_result.record",
    "step.reflect.record",
    "step.span.record",
    # Spine self-observation (ADR-2026-09-02-i17-traceback)
    "spine.i17.rejected",
    "spine.producer.failure",
    "phase_graph.instrument.coverage",
    # Team (PR-6)
    "team.casting.started",
    "team.casting.completed",
    "team.casting.failed",
    "team.delegation.issued",
    "team.delegation.completed",
    "team.delegation.cache_hit",
    "team.message.published",
    # Perception (PR-6)
    "perception.observe",
    "attention.focus",
    "attention.blur",
    "perception.signal.detected",
    "perception.fused",
    "perception.artifact.built",
    # Control (PR-6)
    "control.dispatch",
    "control.invoke",
    "control.signal",
    "control.approve.request",
    "control.approve.response",
    "control.deny",
    "control.revoke",
    "control.pause",
    "control.resume",
    "control.stop",
    "control.accept",
    # Boot (PR-6)
    "boot.profile.resolved",
    "boot.plugin.fiber.spawned",
    "boot.observability.assembled",
    # Runtime observed (PR-6)
    "runtime.observed",
)


_SPINE_EP_TO_CATEGORY: dict[str, str] = {
    # Cognition（PR-2 全量；试点已含 brain.perceive.start）
    "brain.perceive.start": "spine.cognition.brain.perceive.start",
    "brain.perceive.end": "spine.cognition.brain.perceive.end",
    "brain.think.start": "spine.cognition.brain.think.start",
    "brain.think.end": "spine.cognition.brain.think.end",
    "brain.gate.start": "spine.cognition.brain.gate.start",
    "brain.gate.end": "spine.cognition.brain.gate.end",
    "critic.eval.start": "spine.cognition.critic.eval.start",
    "critic.eval.end": "spine.cognition.critic.eval.end",
    "reasoner.reason.start": "spine.cognition.reasoner.reason.start",
    "reasoner.reason.end": "spine.cognition.reasoner.reason.end",
    "prompt_assembler.assemble.start": "spine.cognition.prompt_assembler.assemble.start",
    "prompt_assembler.assemble.end": "spine.cognition.prompt_assembler.assemble.end",
    "synthesizer.merge": "spine.cognition.synthesizer.merge",
    "skill_router.route": "spine.cognition.skill_router.route",
    "memory.read": "spine.cognition.memory.read",
    "memory.write": "spine.cognition.memory.write",
    # Body（PR-3）
    "body.tool.execute.start": "spine.body.tool.execute.start",
    "body.tool.execute.end": "spine.body.tool.execute.end",
    "body.tool.retry": "spine.body.tool.retry",
    "body.sandbox.enter": "spine.body.sandbox.enter",
    "body.sandbox.exit": "spine.body.sandbox.exit",
    # Lifecycle（PR-3）
    "lifecycle.finally": "spine.lifecycle.finally",
    # LLM（PR-3）
    "llm.call.start": "spine.llm.call.start",
    "llm.call.end": "spine.llm.call.end",
    "llm.stream.token": "spine.llm.stream.token",
    "llm.stream.stall": "spine.llm.stream.stall",
    "llm.request.header": "spine.llm.request.header",
    # Exception（PR-3）
    "exception.caught": "spine.exception.caught",
    "exception.finally": "spine.exception.finally",
    # Runtime observed（PR-3 与 exception 一起迁；旧 runtime.py 整文件删前迁齐）
    "runtime.reducer.apply": "spine.runtime.reducer.apply",
    "runtime.checkpoint.create": "spine.runtime.checkpoint.create",
    "runtime.resume.start": "spine.runtime.resume.start",
    "runtime.resume.end": "spine.runtime.resume.end",
    "runtime.event_publisher.publish": "spine.runtime.event_publisher.publish",
    # Transport / kernel / agent_loop / agent / loop（PR-4）
    "transport.route.enter": "spine.transport.route.enter",
    "transport.route.exit": "spine.transport.route.exit",
    "transport.sse.publish": "spine.transport.sse.publish",
    "kernel.boot.start": "spine.kernel.boot.start",
    "kernel.boot.completed": "spine.kernel.boot.completed",
    "kernel.run.start": "spine.kernel.run.start",
    "kernel.run.stop": "spine.kernel.run.stop",
    "kernel.run.cancelled": "spine.kernel.run.cancelled",
    "agent_loop.iteration.start": "spine.agent_loop.iteration.start",
    "agent_loop.iteration.end": "spine.agent_loop.iteration.end",
    "loop.fork": "spine.loop.fork",
    "agent.spawn": "spine.agent.spawn",
    "agent.iteration": "spine.agent.iteration",
    "agent.final": "spine.agent.final",
    # Writable matrix (PR-5)
    "writable.step.start": "spine.writable.step.start",
    "writable.step.end": "spine.writable.step.end",
    "writable.segment.start": "spine.writable.segment.start",
    "writable.segment.end": "spine.writable.segment.end",
    "writable.iteration.halt": "spine.writable.iteration.halt",
    "writable.iteration.closing": "spine.writable.iteration.closing",
    "writable.iteration.close": "spine.writable.iteration.close",
    # Phase (PR-5)
    "perceive.phase.fold": "spine.perceive.phase.fold",
    "phase.perceive.fold": "spine.phase.perceive.fold",
    "phase.think.fold": "spine.phase.think.fold",
    "phase.gate.fold": "spine.phase.gate.fold",
    "phase.remember.fold": "spine.phase.remember.fold",
    "phase.stop.fold": "spine.phase.stop.fold",
    "phase.reflect.fold": "spine.phase.reflect.fold",
    "phase.act.fold.start": "spine.phase.act.fold.start",
    "phase.act.fold.end": "spine.phase.act.fold.end",
    "phase.act.fold": "spine.phase.act.fold",
    "phase.tool.call.start": "spine.phase.tool.call.start",
    "phase.tool.call.end": "spine.phase.tool.call.end",
    "phase.tool.denied": "spine.phase.tool.denied",
    # Phase graph (PR-5)
    "phase_graph.node.start": "spine.phase_graph.node.start",
    "phase_graph.node.end": "spine.phase_graph.node.end",
    "phase_graph.edge.transit": "spine.phase_graph.edge.transit",
    "phase_graph.instrument.coverage": "spine.phase_graph.instrument.coverage",
    # Team (PR-6)
    "team.casting.started": "spine.team.casting.started",
    "team.casting.completed": "spine.team.casting.completed",
    "team.casting.failed": "spine.team.casting.failed",
    "team.delegation.issued": "spine.team.delegation.issued",
    "team.delegation.completed": "spine.team.delegation.completed",
    "team.delegation.cache_hit": "spine.team.delegation.cache_hit",
    "team.message.published": "spine.team.message.published",
    # Perception (PR-6)
    "perception.observe": "spine.perception.observe",
    "attention.focus": "spine.perception.attention.focus",
    "attention.blur": "spine.perception.attention.blur",
    "perception.signal.detected": "spine.perception.signal.detected",
    "perception.fused": "spine.perception.fused",
    "perception.artifact.built": "spine.perception.artifact.built",
    # Control (PR-6)
    "control.dispatch": "spine.control.dispatch",
    "control.invoke": "spine.control.invoke",
    "control.signal": "spine.control.signal",
    "control.approve.request": "spine.control.approve.request",
    "control.approve.response": "spine.control.approve.response",
    "control.deny": "spine.control.deny",
    "control.revoke": "spine.control.revoke",
    "control.pause": "spine.control.pause",
    "control.resume": "spine.control.resume",
    "control.stop": "spine.control.stop",
    "control.accept": "spine.control.accept",
    # Boot (PR-6)
    "boot.profile.resolved": "spine.boot.profile.resolved",
    "boot.plugin.fiber.spawned": "spine.boot.plugin.fiber.spawned",
    "boot.observability.assembled": "spine.boot.observability.assembled",
    # Runtime observed (PR-6)
    "runtime.observed": "spine.runtime.observed",
}


class SpineEventPayload(EventPayload):
    """spine 壳类 payload（ADR-0181 D2）。

    承载：
    - ``execution_point``：SPINE_EXECUTION_POINTS 闭集中的字符串（决定 category）
    - ``channel``：原 EventRecord.channel（fact/control/error/diagnostic）
    - ``payload``：原 caller_payload（dict）
    - chain 字段（span_id / parent_span_id / sequence / epoch / prev_event_hash）：
      由 SpineContext 注入；spine_chain_sink 落盘前算 hash chain
    - ``category``（pydantic 父类必填）：由 execution_point 派生（业务方不传）
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Category
    execution_point: str
    channel: str = "fact"
    payload: dict[str, Any] = Field(default_factory=dict)
    span_id: str | None = None
    parent_span_id: str | None = None
    sequence: int = 0
    epoch: int = 0
    prev_event_hash: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _derive_category_from_ep(cls, data: Any) -> Any:
        """业务方只传 execution_point；category 由 _SPINE_EP_TO_CATEGORY 派生注入。"""
        if isinstance(data, dict) and "category" not in data and "execution_point" in data:
            ep = data["execution_point"]
            cat_str = _SPINE_EP_TO_CATEGORY.get(ep)
            if cat_str is None:
                raise ValueError(f"spine EP {ep!r} 未登记 category 映射（ADR-0181 后续 PR 补）")
            data = {**data, "category": Category(cat_str)}
        return data

    @model_validator(mode="after")
    def _validate_spine_fields(self) -> SpineEventPayload:
        if self.execution_point not in SPINE_EXECUTION_POINTS:
            raise ValueError(
                f"UnknownSpineExecutionPoint({self.execution_point!r}): "
                f"not in SPINE_EXECUTION_POINTS whitelist"
            )
        expected_category = _SPINE_EP_TO_CATEGORY.get(self.execution_point)
        if expected_category is None:
            raise ValueError(
                f"spine EP {self.execution_point!r} 未登记 category 映射（ADR-0181 后续 PR 补）"
            )
        if self.category.value != expected_category:
            raise ValueError(
                f"spine EP {self.execution_point!r} 必须用 category={expected_category!r}；"
                f"got {self.category.value!r}"
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
