"""遥测词汇目录 —— 全框架 span/event 命名的单一事实源。

结构约定：
- 每个词条（SpanName/EventName）在 ``TELEMETRY_CATALOG`` 中登记
  域（domain）/ 种类（kind）/ 唯一发射模块（emitter）/ 必备属性；
- 守卫测试强制「一词条一发射点」：发射位置必须与 catalog 登记的
  emitter 前缀一致，禁止多点乱发与词汇蔓延；
- 新增词条 = 枚举一行 + catalog 一行，缺一即 CI 失败。

域划分（层次模型）：
    run.*        运行域 —— 一次 run 的根与场景卡
    team.*       团队域 —— 编排/委派/轮次/汇总
    loop.phase.* 认知域 —— perceive/think/act/reflect 四相
    资源域        —— llm.chat / tool.execute / memory.* / transport.*
    事件域        —— 业务事实（决策/委派/拒绝/降级/完成）
"""

from __future__ import annotations

from enum import Enum


class SpanName(str, Enum):
    """稳定 span 名（全链路可观测）。"""

    # ── 运行域 ──
    RUN_AGENT = "run.agent"
    RUN_TEAM = "run.team"
    RUN_PLAN = "run.plan"  # run 入口场景卡（嵌套于 run.team / run.agent）
    # ── 团队域 ──
    TEAM_STRATEGY = "team.strategy"
    TEAM_MEMBER_INVOKE = "team.member_invoke"
    TEAM_ROUND = "team.round"
    TEAM_SYNTHESIS = "team.synthesis"
    # ── 认知域 ──
    LOOP_PHASE_PERCEIVE = "loop.phase.perceive"
    LOOP_PHASE_THINK = "loop.phase.think"
    LOOP_PHASE_ACT = "loop.phase.act"
    LOOP_PHASE_REFLECT = "loop.phase.reflect"
    # ── 资源域 ──
    LLM_CHAT = "llm.chat"
    TOOL_EXECUTE = "tool.execute"
    MEMORY_READ = "memory.read"
    MEMORY_WRITE = "memory.write"
    TRANSPORT_REQUEST = "transport.request"
    TRANSPORT_RESPONSE = "transport.response"
    # 委派幂等短路（无传输往返）
    DELEGATE_CACHE_HIT = "delegate.cache_hit"
    # hook on_error 发射的错误 span
    ERROR = "error"


class EventName(str, Enum):
    """业务事件名（瞬时事实，挂在当前 span 下）。"""

    # ── 决策域 ──
    DECISION_MADE = "decision.made"
    # ── 委派域 ──
    DELEGATE_REQUESTED = "delegate.requested"
    # ── 执行域 ──
    TOOL_DENIED = "tool.denied"
    ACTION_DEGRADED = "action.degraded"
    STEP_COMPLETED = "step.completed"
    # ── 运行域 ──
    RUN_COMPLETED = "run.completed"


# ── 属性键（封闭词表，禁止裸字符串）────────────────────
ATTR_EVENT = "event"
ATTR_AGENT_ROLE = "agent_role"
ATTR_FROM_ROLE = "from_role"
ATTR_TEAM_ID = "team_id"
ATTR_SESSION_ID = "session_id"
ATTR_STRATEGY_KEY = "strategy_key"
ATTR_MANDATE = "mandate"
ATTR_STEP = "step"
ATTR_ACTION_TYPE = "action_type"
ATTR_TOOL_NAME = "tool_name"
ATTR_DELEGATE_TARGET = "delegate_target"
ATTR_DELEGATE_COUNT = "delegate_count"
ATTR_SUBTASK_PREVIEW = "subtask_preview"
ATTR_CALLER_ROLE = "caller_role"
ATTR_CALLEE_ROLE = "callee_role"
ATTR_ROUND = "round"
ATTR_MAX_ROUNDS = "max_rounds"
ATTR_CANDIDATE_COUNT = "candidate_count"
ATTR_SYNTHESIS_METHOD = "synthesis_method"
ATTR_MODEL = "model"
ATTR_OK = "ok"
ATTR_STATUS = "status"
ATTR_PROTOCOL = "protocol"
ATTR_LATENCY_MS = "latency_ms"
ATTR_OBJECTIVE_PREVIEW = "objective_preview"
ATTR_MEMBERS = "members"  # 逗号分隔角色
ATTR_LEAD_ROLE = "lead_role"
ATTR_PLAN_STEPS = "plan_steps"  # " | " 连接
ATTR_LEVEL = "level"
# LLM I/O
ATTR_PROMPT_PREVIEW = "prompt_preview"
ATTR_RESPONSE_PREVIEW = "response_preview"
ATTR_PROMPT_CHARS = "prompt_chars"
ATTR_RESPONSE_CHARS = "response_chars"
ATTR_PROMPT_TOKENS = "prompt_tokens"
ATTR_COMPLETION_TOKENS = "completion_tokens"
ATTR_PROMPT_TEMPLATE = "prompt_template"
# 记忆（知识检索）
ATTR_MEMORY_LAYER = "memory_layer"
ATTR_MEMORY_KEY_PREVIEW = "memory_key_preview"
ATTR_HIT = "hit"

# HookEvent → loop phase span（认知生命周期）
HOOK_TO_PHASE_SPAN: dict[str, str] = {
    "pre_perceive": SpanName.LOOP_PHASE_PERCEIVE.value,
    "post_perceive": SpanName.LOOP_PHASE_PERCEIVE.value,
    "pre_think": SpanName.LOOP_PHASE_THINK.value,
    "post_think": SpanName.LOOP_PHASE_THINK.value,
    "pre_act": SpanName.LOOP_PHASE_ACT.value,
    "post_act": SpanName.LOOP_PHASE_ACT.value,
    "pre_reflect": SpanName.LOOP_PHASE_REFLECT.value,
    "post_reflect": SpanName.LOOP_PHASE_REFLECT.value,
}
