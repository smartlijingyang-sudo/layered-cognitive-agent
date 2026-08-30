"""遥测词汇目录 —— SpanName/EventName 词条的登记簿（单一事实源）。

每个词条登记：域（domain）/ 种类（kind）/ 唯一发射模块（emitter）/
必备属性。守卫测试强制「一词条一发射点」；新增词条 = 枚举一行 +
catalog 一行，缺一即 CI 失败。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from lca.contracts.atoms.telemetry import (
    ATTR_AGENT_ROLE,
    ATTR_CALLEE_ROLE,
    ATTR_DELEGATE_TARGET,
    ATTR_MEMORY_LAYER,
    ATTR_MODEL,
    ATTR_ROUND,
    ATTR_STEP,
    ATTR_TOOL_NAME,
    EventName,
    SpanName,
)


class VocabDomain(str, Enum):
    """词汇所属语义域。"""

    RUN = "run"
    TEAM = "team"
    COGNITIVE = "cognitive"
    RESOURCE = "resource"
    EVENT = "event"


class VocabKind(str, Enum):
    """词汇种类：span（有持续时长）或 event（瞬时事实）。"""

    SPAN = "span"
    EVENT = "event"


@dataclass(frozen=True)
class VocabDef:
    """词汇条目登记：域 / 种类 / 唯一发射模块 / 必备属性 / 说明。

    ``emitter`` 是发射模块的点分路径前缀；守卫测试用它强制
    「一词条一发射点」。
    """

    domain: VocabDomain
    kind: VocabKind
    emitter: str
    required_attrs: tuple[str, ...] = field(default_factory=tuple)
    description: str = ""


def _span(
    domain: VocabDomain, emitter: str, *, required: tuple[str, ...] = (), desc: str = ""
) -> VocabDef:
    return VocabDef(domain, VocabKind.SPAN, emitter, required, desc)


def _event(emitter: str, *, required: tuple[str, ...] = (), desc: str = "") -> VocabDef:
    return VocabDef(VocabDomain.EVENT, VocabKind.EVENT, emitter, required, desc)


#: 词汇目录 —— 单一事实源（守卫测试输入 / 文档 / Langfuse 映射配置源）
TELEMETRY_CATALOG: dict[str, VocabDef] = {
    # ── 运行域：run 容器（ADR-0037 起由 OtelProjector 从 journal 投影）──
    SpanName.RUN_AGENT.value: _span(
        VocabDomain.RUN,
        "lca.infrastructure.observability.journal.otel.projector",
        desc="单 agent 运行根（journal AgentRunStarted/Finished 投影）",
    ),
    SpanName.RUN_TEAM.value: _span(
        VocabDomain.RUN,
        "lca.infrastructure.observability.journal.otel.projector",
        desc="团队运行根（journal TeamRunStarted/Finished 投影）",
    ),
    # ── 团队域：编排层 ──
    SpanName.DELEGATION.value: _span(
        VocabDomain.TEAM,
        "lca.infrastructure.observability.journal.otel.projector",
        required=(ATTR_CALLEE_ROLE,),
        desc="委派往返（journal 投影；包住成员全程，ADR-0037）",
    ),
    SpanName.TEAM_ROUND.value: _span(
        VocabDomain.TEAM,
        "lca.agent.orchestration_strategies",
        required=(ATTR_ROUND,),
        desc="对等协作轮次",
    ),
    SpanName.TEAM_SYNTHESIS.value: _span(
        VocabDomain.TEAM,
        "lca.agent.orchestration_strategies",
        desc="结果汇总",
    ),
    # ── 认知域：hook 边界自动发射 ──
    SpanName.LOOP_PHASE_PERCEIVE.value: _span(
        VocabDomain.COGNITIVE,
        "lca.cognition.hook_registry",
        required=(ATTR_AGENT_ROLE, ATTR_STEP),
        desc="感知相位",
    ),
    SpanName.LOOP_PHASE_THINK.value: _span(
        VocabDomain.COGNITIVE,
        "lca.cognition.hook_registry",
        required=(ATTR_AGENT_ROLE, ATTR_STEP),
        desc="思考相位",
    ),
    SpanName.LOOP_PHASE_ACT.value: _span(
        VocabDomain.COGNITIVE,
        "lca.cognition.hook_registry",
        required=(ATTR_AGENT_ROLE, ATTR_STEP),
        desc="行动相位",
    ),
    SpanName.LOOP_PHASE_REFLECT.value: _span(
        VocabDomain.COGNITIVE,
        "lca.cognition.hook_registry",
        required=(ATTR_AGENT_ROLE, ATTR_STEP),
        desc="反思相位",
    ),
    # ── 资源域：适配器/边界发射 ──
    SpanName.LLM_CHAT.value: _span(
        VocabDomain.RESOURCE,
        "lca.infrastructure.observability.adapters",
        required=(ATTR_MODEL,),
        desc="LLM 调用（generation）",
    ),
    SpanName.TOOL_EXECUTE.value: _span(
        VocabDomain.RESOURCE,
        "lca.cognition.body.safe_executor",
        required=(ATTR_TOOL_NAME,),
        desc="工具执行",
    ),
    SpanName.MEMORY_READ.value: _span(
        VocabDomain.RESOURCE,
        "lca.infrastructure.observability.memory_adapter",
        required=(ATTR_MEMORY_LAYER,),
        desc="记忆读取（知识检索）",
    ),
    SpanName.MEMORY_WRITE.value: _span(
        VocabDomain.RESOURCE,
        "lca.infrastructure.observability.memory_adapter",
        required=(ATTR_MEMORY_LAYER,),
        desc="记忆写入",
    ),
    SpanName.TRANSPORT_REQUEST.value: _span(
        VocabDomain.RESOURCE,
        "lca.infrastructure.transport.invocation",
        desc="传输请求",
    ),
    SpanName.TRANSPORT_RESPONSE.value: _span(
        VocabDomain.RESOURCE,
        "lca.infrastructure.transport.invocation",
        desc="传输响应",
    ),
    SpanName.DELEGATE_CACHE_HIT.value: _event(
        "lca.infrastructure.observability.journal.otel.projector",
        desc="委派幂等短路（journal DelegationCacheHit 投影为 run span event，ADR-0037）",
    ),
    SpanName.ERROR.value: _span(
        VocabDomain.RESOURCE,
        "lca.cognition.hook_registry",
        desc="hook on_error 错误 span",
    ),
    # ── 事件域 ──
    EventName.DECISION_MADE.value: _event(
        "lca.cognition.body.action_handlers",
        desc="决策落地（委派/工具/回答动作分发点）",
    ),
    EventName.DELEGATE_REQUESTED.value: _event(
        "lca.agent.member_invoke",
        required=(ATTR_DELEGATE_TARGET,),
        desc="委派发起",
    ),
    EventName.TOOL_DENIED.value: _event(
        "lca.cognition.body.safe_executor",
        required=(ATTR_TOOL_NAME,),
        desc="工具调用被安全策略拒绝",
    ),
    EventName.ACTION_DEGRADED.value: _event(
        "lca.runtime.event_emission",
        desc="动作降级（journal 直写）",
    ),
    EventName.STEP_COMPLETED.value: _event(
        "lca.runtime.event_emission",
        required=(ATTR_STEP,),
        desc="步骤完成（journal 直写）",
    ),
}
