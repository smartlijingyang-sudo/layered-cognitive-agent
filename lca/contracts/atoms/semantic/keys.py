"""框架语义键 —— Observation.extra / Decision.extra 中的约定字段名与闭集取值。

AgentState 一等字段（final_output / last_error / active_template /
MEMBER_STATUS_PROMPT_REMOVED）不再走字符串键。仅 **扩展袋** 使用本模块常量，
禁止在业务代码中书写裸字符串字面量。

闭集取值的多值折叠（`fold_failure_kinds`）与取值本身同处一地：折叠语义属于
词表，不属于任何一个调用方。
"""

from __future__ import annotations

from collections.abc import Iterable

# Observation.extra
FAILURE_KIND = "failure_kind"
OBS_DEGRADED_FROM = "degraded_from_action_type"
OBS_TASK_ID = "task_id"
OBS_TASK_IDS = "task_ids"
OBS_MEMBER_RESULTS = "member_results"
OBS_MEMBER_SUBTASKS = "member_subtasks"
OBS_RESULT_KIND = "result_kind"
OBS_TOOL_RESULTS = "tool_results"
OBS_CACHE_HIT = "cache_hit"
OBS_HANDOFF = "handoff"
# 委派完成质量（ADR-0049 证据平面）
OBS_COMPLETION_QUALITY = "completion_quality"
OBS_DELEGATION_ID = "delegation_id"

# completion_quality 取值
COMPLETION_FULL = "full"
COMPLETION_PARTIAL = "partial"
COMPLETION_EMPTY = "empty"

# MemoryRecord.metadata（委派结果归属）
META_ROLE = "role"
META_SUBTASK = "subtask"
META_STEP = "step"
META_TASK_ID = "task_id"

# Decision.extra
EVAL_CONFLICTS = "eval_conflicts"
# 工具调用 wire 防腐（ADR-0047）：adapter 写入 JSON 顶层，parser 拷入 Decision.extra
TOOL_WIRE_STATUS = "tool_wire_status"
TOOL_WIRE_REASON = "tool_wire_reason"
TOOL_WIRE_RAW_PREVIEW = "tool_wire_raw_preview"
TOOL_WIRE_FINISH_REASON = "tool_wire_finish_reason"

# tool_wire_status 取值
TOOL_WIRE_OK = "ok"
TOOL_WIRE_INCOMPLETE = "incomplete"
TOOL_WIRE_INVALID = "invalid"

# failure_kind 取值
FAILURE_KIND_VALIDATION = "validation"
FAILURE_KIND_EXECUTION = "execution"
FAILURE_KIND_TRANSIENT = "transient"
FAILURE_KIND_TOOL_WIRE = "tool_wire"

# 一个 turn fork 出 N 个工具调用时，N 条 per-call Observation 会折成一条聚合
# Observation，聚合体必须仍能回答「有没有工具报告过自己的结果」。越靠前越靠近
# 模型自身（调用本身没成形 → 参数不合法 → 工具在自己的标的物上确定性失败 →
# 基础设施抖动），取最靠前者，使聚合结果与调用顺序和并发调度无关（C8）。
FAILURE_KIND_PRECEDENCE: tuple[str, ...] = (
    FAILURE_KIND_TOOL_WIRE,
    FAILURE_KIND_VALIDATION,
    FAILURE_KIND_EXECUTION,
    FAILURE_KIND_TRANSIENT,
)


def fold_failure_kinds(kinds: Iterable[object]) -> str | None:
    """返回 ``kinds`` 中优先级最高的分类；没有任何非空字符串时返回 ``None``。

    ``kinds`` 直接吃 ``Observation.extra`` 的取值（``Any``），非字符串与空串
    一律视为「这一分量没有分类」，调用方不必自己再判类型。

    ``None`` 是承载语义的：``EffectReceipt.failure_kind is None`` 表示 host
    根本没能把 effect 派出去、没有任何工具报告过结果，
    ``act.observe.terminate_decide`` 据此收口 run（ADR-0230 Amendment）。
    因此只要有一个分量带着分类，聚合体就必须带着分类。

    不在 ``FAILURE_KIND_PRECEDENCE`` 内的非空取值仍然算「已分类」，排在已知
    取值之后并按字典序比较——扩充词表不会把一个批次悄悄降级成 host 派发失败。
    """
    present = [kind for kind in kinds if isinstance(kind, str) and kind]
    if not present:
        return None
    unknown = len(FAILURE_KIND_PRECEDENCE)
    return min(
        present,
        key=lambda kind: (
            FAILURE_KIND_PRECEDENCE.index(kind) if kind in FAILURE_KIND_PRECEDENCE else unknown,
            kind,
        ),
    )
