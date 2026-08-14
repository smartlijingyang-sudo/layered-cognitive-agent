"""框架语义键 —— Observation.extra / Decision.extra 中的约定字段名。

AgentState 一等字段（final_output / last_error / active_template /
MEMBER_STATUS_PROMPT_REMOVED）不再走字符串键。仅 **扩展袋** 使用本模块常量，
禁止在业务代码中书写裸字符串字面量。
"""

from __future__ import annotations

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
