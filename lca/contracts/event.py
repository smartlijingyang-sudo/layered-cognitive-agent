"""事件层 v2 协议 —— ADR-0180 配套。

机制实现见 :mod:`lca_kernel.events`（kernel 元层插件）。
本模块只描述协议骨架：Category 闭集、EventPayload pydantic 基类、Plane 闭集。

不变量：
- D2：Category 由机制在 boot 时从 ``lca_kernel/events/config/**/*.yaml`` 加载；
       本枚举给出试点最小闭集，PR 2–13 逐个补齐。
- D3：每个 EventPayload 必须声明 ``category`` 字段，子类覆盖 default。
- D4：本模块不导出 send/subscribe；那由机制 :class:`lca_kernel.events.mechanism.EventMechanism` 暴露。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict

# ── 闭集：category 与 plane ──────────────────────────────────────────────


class Category(str, Enum):
    """事件 category 闭集（ADR-0180 D2）。

    本枚举是协议层最小集；机制 boot 时从 ``lca_kernel/events/config/**/*.yaml``
    加载完整 SSOT 矩阵，运行期拒收未登记的 category。
    新增必须有 ADR + 配套 yaml 行。
    """

    # business/team
    TEAM_CASTING_STARTED = "team.casting.started"
    TEAM_CASTING_COMPLETED = "team.casting.completed"
    TEAM_CASTING_FAILED = "team.casting.failed"
    TEAM_DELEGATION_ISSUED = "team.delegation.issued"
    TEAM_DELEGATION_COMPLETED = "team.delegation.completed"
    TEAM_DELEGATION_CACHE_HIT = "team.delegation.cache_hit"
    TEAM_MESSAGE_PUBLISHED = "team.message.published"
    # observability/spine — ADR-0181 试点 1 个 + PR-2 cognition 余 15
    SPINE_COGNITION_BRAIN_PERCEIVE_START = "spine.cognition.brain.perceive.start"
    SPINE_COGNITION_BRAIN_PERCEIVE_END = "spine.cognition.brain.perceive.end"
    SPINE_COGNITION_BRAIN_THINK_START = "spine.cognition.brain.think.start"
    SPINE_COGNITION_BRAIN_THINK_END = "spine.cognition.brain.think.end"
    SPINE_COGNITION_BRAIN_GATE_START = "spine.cognition.brain.gate.start"
    SPINE_COGNITION_BRAIN_GATE_END = "spine.cognition.brain.gate.end"
    SPINE_COGNITION_CRITIC_EVAL_START = "spine.cognition.critic.eval.start"
    SPINE_COGNITION_CRITIC_EVAL_END = "spine.cognition.critic.eval.end"
    SPINE_COGNITION_REASONER_REASON_START = "spine.cognition.reasoner.reason.start"
    SPINE_COGNITION_REASONER_REASON_END = "spine.cognition.reasoner.reason.end"
    SPINE_COGNITION_PROMPT_ASSEMBLER_ASSEMBLE_START = (
        "spine.cognition.prompt_assembler.assemble.start"
    )
    SPINE_COGNITION_PROMPT_ASSEMBLER_ASSEMBLE_END = (
        "spine.cognition.prompt_assembler.assemble.end"
    )
    SPINE_COGNITION_SYNTHESIZER_MERGE = "spine.cognition.synthesizer.merge"
    SPINE_COGNITION_SKILL_ROUTER_ROUTE = "spine.cognition.skill_router.route"
    SPINE_COGNITION_MEMORY_READ = "spine.cognition.memory.read"
    SPINE_COGNITION_MEMORY_WRITE = "spine.cognition.memory.write"
    # observability/spine — PR-3 body / llm / lifecycle / exception 全迁 12 EP
    SPINE_BODY_TOOL_EXECUTE_START = "spine.body.tool.execute.start"
    SPINE_BODY_TOOL_EXECUTE_END = "spine.body.tool.execute.end"
    SPINE_BODY_TOOL_RETRY = "spine.body.tool.retry"
    SPINE_BODY_SANDBOX_ENTER = "spine.body.sandbox.enter"
    SPINE_BODY_SANDBOX_EXIT = "spine.body.sandbox.exit"
    SPINE_LIFECYCLE_FINALLY = "spine.lifecycle.finally"
    SPINE_LLM_CALL_START = "spine.llm.call.start"
    SPINE_LLM_CALL_END = "spine.llm.call.end"
    SPINE_LLM_STREAM_TOKEN = "spine.llm.stream.token"  # noqa: S105  # enum 名,非密码
    SPINE_LLM_STREAM_STALL = "spine.llm.stream.stall"
    SPINE_LLM_REQUEST_HEADER = "spine.llm.request.header"
    SPINE_EXCEPTION_CAUGHT = "spine.exception.caught"
    SPINE_EXCEPTION_FINALLY = "spine.exception.finally"
    # observability/spine — PR-3 runtime.observed 5 EP（runtime.py 整文件删前迁齐）
    SPINE_RUNTIME_REDUCER_APPLY = "spine.runtime.reducer.apply"
    SPINE_RUNTIME_CHECKPOINT_CREATE = "spine.runtime.checkpoint.create"
    SPINE_RUNTIME_RESUME_START = "spine.runtime.resume.start"
    SPINE_RUNTIME_RESUME_END = "spine.runtime.resume.end"
    SPINE_RUNTIME_EVENT_PUBLISHER_PUBLISH = "spine.runtime.event_publisher.publish"
    # observability/spine — PR-4 transport / kernel / agent_loop / agent / loop 14 EP
    SPINE_TRANSPORT_ROUTE_ENTER = "spine.transport.route.enter"
    SPINE_TRANSPORT_ROUTE_EXIT = "spine.transport.route.exit"
    SPINE_TRANSPORT_SSE_PUBLISH = "spine.transport.sse.publish"
    SPINE_KERNEL_BOOT_START = "spine.kernel.boot.start"
    SPINE_KERNEL_BOOT_COMPLETED = "spine.kernel.boot.completed"
    SPINE_KERNEL_RUN_START = "spine.kernel.run.start"
    SPINE_KERNEL_RUN_STOP = "spine.kernel.run.stop"
    SPINE_KERNEL_RUN_CANCELLED = "spine.kernel.run.cancelled"
    SPINE_AGENT_LOOP_ITERATION_START = "spine.agent_loop.iteration.start"
    SPINE_AGENT_LOOP_ITERATION_END = "spine.agent_loop.iteration.end"
    SPINE_LOOP_FORK = "spine.loop.fork"
    SPINE_AGENT_SPAWN = "spine.agent.spawn"
    SPINE_AGENT_ITERATION = "spine.agent.iteration"
    SPINE_AGENT_FINAL = "spine.agent.final"
    # observability/spine — PR-5 writable / phase / phase_graph 全迁 24 EP
    SPINE_WRITABLE_STEP_START = "spine.writable.step.start"
    SPINE_WRITABLE_STEP_END = "spine.writable.step.end"
    SPINE_WRITABLE_SEGMENT_START = "spine.writable.segment.start"
    SPINE_WRITABLE_SEGMENT_END = "spine.writable.segment.end"
    SPINE_WRITABLE_ITERATION_HALT = "spine.writable.iteration.halt"
    SPINE_WRITABLE_ITERATION_CLOSING = "spine.writable.iteration.closing"
    SPINE_WRITABLE_ITERATION_CLOSE = "spine.writable.iteration.close"
    SPINE_PERCEIVE_PHASE_FOLD = "spine.perceive.phase.fold"
    SPINE_PHASE_PERCEIVE_FOLD = "spine.phase.perceive.fold"
    SPINE_PHASE_THINK_FOLD = "spine.phase.think.fold"
    SPINE_PHASE_GATE_FOLD = "spine.phase.gate.fold"
    SPINE_PHASE_REMEMBER_FOLD = "spine.phase.remember.fold"
    SPINE_PHASE_STOP_FOLD = "spine.phase.stop.fold"
    SPINE_PHASE_REFLECT_FOLD = "spine.phase.reflect.fold"
    SPINE_PHASE_ACT_FOLD_START = "spine.phase.act.fold.start"
    SPINE_PHASE_ACT_FOLD_END = "spine.phase.act.fold.end"
    SPINE_PHASE_ACT_FOLD = "spine.phase.act.fold"
    SPINE_PHASE_TOOL_CALL_START = "spine.phase.tool.call.start"
    SPINE_PHASE_TOOL_CALL_END = "spine.phase.tool.call.end"
    SPINE_PHASE_TOOL_DENIED = "spine.phase.tool.denied"
    SPINE_PHASE_GRAPH_NODE_START = "spine.phase_graph.node.start"
    SPINE_PHASE_GRAPH_NODE_END = "spine.phase_graph.node.end"
    SPINE_PHASE_GRAPH_EDGE_TRANSIT = "spine.phase_graph.edge.transit"
    SPINE_PHASE_GRAPH_INSTRUMENT_COVERAGE = "spine.phase_graph.instrument.coverage"


class Plane(str, Enum):
    """事件语义平面（沿用 ADR-0063 三平面）。"""

    SURFACE = "surface"
    STRUCTURAL = "structural"
    EXPLANATION = "explanation"
    OBSERVABILITY = "observability"


# 试点 category 与 plane 的映射（与 yaml SSOT 保持同步；boot 时机制会校验一致）。
CATEGORY_DEFAULT_PLANE: dict[Category, Plane] = {
    Category.TEAM_DELEGATION_CACHE_HIT: Plane.STRUCTURAL,
    Category.SPINE_COGNITION_BRAIN_PERCEIVE_START: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_BRAIN_PERCEIVE_END: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_BRAIN_THINK_START: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_BRAIN_THINK_END: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_BRAIN_GATE_START: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_BRAIN_GATE_END: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_CRITIC_EVAL_START: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_CRITIC_EVAL_END: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_REASONER_REASON_START: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_REASONER_REASON_END: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_PROMPT_ASSEMBLER_ASSEMBLE_START: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_PROMPT_ASSEMBLER_ASSEMBLE_END: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_SYNTHESIZER_MERGE: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_SKILL_ROUTER_ROUTE: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_MEMORY_READ: Plane.OBSERVABILITY,
    Category.SPINE_COGNITION_MEMORY_WRITE: Plane.OBSERVABILITY,
    # PR-3 body / llm / lifecycle / exception 全迁
    Category.SPINE_BODY_TOOL_EXECUTE_START: Plane.OBSERVABILITY,
    Category.SPINE_BODY_TOOL_EXECUTE_END: Plane.OBSERVABILITY,
    Category.SPINE_BODY_TOOL_RETRY: Plane.OBSERVABILITY,
    Category.SPINE_BODY_SANDBOX_ENTER: Plane.OBSERVABILITY,
    Category.SPINE_BODY_SANDBOX_EXIT: Plane.OBSERVABILITY,
    Category.SPINE_LIFECYCLE_FINALLY: Plane.OBSERVABILITY,
    Category.SPINE_LLM_CALL_START: Plane.OBSERVABILITY,
    Category.SPINE_LLM_CALL_END: Plane.OBSERVABILITY,
    Category.SPINE_LLM_STREAM_TOKEN: Plane.OBSERVABILITY,
    Category.SPINE_LLM_STREAM_STALL: Plane.OBSERVABILITY,
    Category.SPINE_LLM_REQUEST_HEADER: Plane.OBSERVABILITY,
    Category.SPINE_EXCEPTION_CAUGHT: Plane.OBSERVABILITY,
    Category.SPINE_EXCEPTION_FINALLY: Plane.OBSERVABILITY,
    Category.SPINE_RUNTIME_REDUCER_APPLY: Plane.OBSERVABILITY,
    Category.SPINE_RUNTIME_CHECKPOINT_CREATE: Plane.OBSERVABILITY,
    Category.SPINE_RUNTIME_RESUME_START: Plane.OBSERVABILITY,
    Category.SPINE_RUNTIME_RESUME_END: Plane.OBSERVABILITY,
    Category.SPINE_RUNTIME_EVENT_PUBLISHER_PUBLISH: Plane.OBSERVABILITY,
    Category.SPINE_TRANSPORT_ROUTE_ENTER: Plane.OBSERVABILITY,
    Category.SPINE_TRANSPORT_ROUTE_EXIT: Plane.OBSERVABILITY,
    Category.SPINE_TRANSPORT_SSE_PUBLISH: Plane.OBSERVABILITY,
    Category.SPINE_KERNEL_BOOT_START: Plane.OBSERVABILITY,
    Category.SPINE_KERNEL_BOOT_COMPLETED: Plane.OBSERVABILITY,
    Category.SPINE_KERNEL_RUN_START: Plane.OBSERVABILITY,
    Category.SPINE_KERNEL_RUN_STOP: Plane.OBSERVABILITY,
    Category.SPINE_KERNEL_RUN_CANCELLED: Plane.OBSERVABILITY,
    Category.SPINE_AGENT_LOOP_ITERATION_START: Plane.OBSERVABILITY,
    Category.SPINE_AGENT_LOOP_ITERATION_END: Plane.OBSERVABILITY,
    Category.SPINE_LOOP_FORK: Plane.OBSERVABILITY,
    Category.SPINE_AGENT_SPAWN: Plane.OBSERVABILITY,
    Category.SPINE_AGENT_ITERATION: Plane.OBSERVABILITY,
    Category.SPINE_AGENT_FINAL: Plane.OBSERVABILITY,
    Category.SPINE_WRITABLE_STEP_START: Plane.OBSERVABILITY,
    Category.SPINE_WRITABLE_STEP_END: Plane.OBSERVABILITY,
    Category.SPINE_WRITABLE_SEGMENT_START: Plane.OBSERVABILITY,
    Category.SPINE_WRITABLE_SEGMENT_END: Plane.OBSERVABILITY,
    Category.SPINE_WRITABLE_ITERATION_HALT: Plane.OBSERVABILITY,
    Category.SPINE_WRITABLE_ITERATION_CLOSING: Plane.OBSERVABILITY,
    Category.SPINE_WRITABLE_ITERATION_CLOSE: Plane.OBSERVABILITY,
    Category.SPINE_PERCEIVE_PHASE_FOLD: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_PERCEIVE_FOLD: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_THINK_FOLD: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_GATE_FOLD: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_REMEMBER_FOLD: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_STOP_FOLD: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_REFLECT_FOLD: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_ACT_FOLD_START: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_ACT_FOLD_END: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_ACT_FOLD: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_TOOL_CALL_START: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_TOOL_CALL_END: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_TOOL_DENIED: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_GRAPH_NODE_START: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_GRAPH_NODE_END: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_GRAPH_EDGE_TRANSIT: Plane.OBSERVABILITY,
    Category.SPINE_PHASE_GRAPH_INSTRUMENT_COVERAGE: Plane.OBSERVABILITY,
}


def default_plane(category: Category) -> Plane:
    """由 category 推导 plane；未登记 → ValueError。"""
    try:
        return CATEGORY_DEFAULT_PLANE[category]
    except KeyError as exc:
        msg = f"Category.{category.name} 未登记 plane 映射；新增必须在 yaml + 本枚举同步登记"
        raise ValueError(msg) from exc


# ── Pydantic payload 集（D3：业务方构造 typed payload）─────────────────


class EventPayload(BaseModel):
    """所有事件 payload 的基类。

    业务方构造一个具体子类（typed 字段），调机制 :func:`EventMechanism.send`；
    机制读 ``payload.category`` 决定路由，不要求业务方传 category。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: Category
    """子类必须覆盖：声明本 payload 归属的 category 闭集值。"""


class TeamDelegationCacheHit(EventPayload):
    """试点 payload：委派幂等短路命中（对应旧 DelegationCacheHit）。

    publishers（SSOT yaml）: ``delegation_cache``
    subscribers（SSOT yaml）: ``journal_sink``, ``console_projector``, ``cursor_consumer``
    """

    category: Category = Category.TEAM_DELEGATION_CACHE_HIT
    callee_role: str
    subtask: str
    step: int


# ── 试点范围显式记录（用于 lint 守护）─────────────────────────────────────

PILOT_PAYLOADS: tuple[type[EventPayload], ...] = (TeamDelegationCacheHit,)
"""试点 PR 仅覆盖 TeamDelegationCacheHit；其余 payload 在后续 PR 补齐。"""

PILOT_CATEGORIES: frozenset[Category] = frozenset(
    {payload.model_fields["category"].default for payload in PILOT_PAYLOADS}
)
"""由 PILOT_PAYLOADS 派生；防止 pilot category 与 pilot payload 漂移。"""


__all__ = [
    "PILOT_CATEGORIES",
    "PILOT_PAYLOADS",
    "Category",
    "EventPayload",
    "Plane",
    "TeamDelegationCacheHit",
    "default_plane",
]
