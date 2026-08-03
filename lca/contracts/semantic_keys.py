"""框架语义键 —— Observation.extra / Decision.extra 中的约定字段名。

AgentState 一等字段（final_output / last_error / active_template /
MEMBER_STATUS_PROMPT_REMOVED）不再走字符串键。仅 **扩展袋** 使用本模块常量，
禁止在业务代码中书写裸字符串字面量。
"""

from __future__ import annotations

# Observation.extra
FAILURE_KIND = "failure_kind"
FALLBACK_DEGRADED_FROM = "degraded_from_action_type"
OBS_TASK_ID = "task_id"
OBS_TASK_IDS = "task_ids"
OBS_MEMBER_RESULTS = "member_results"
OBS_HANDOFF = "handoff"

# Decision.extra
ORIGINAL_ACTION_TYPE = "original_action_type"
EVAL_CONFLICTS = "eval_conflicts"

# failure_kind 取值
FAILURE_KIND_VALIDATION = "validation"
FAILURE_KIND_EXECUTION = "execution"
FAILURE_KIND_TRANSIENT = "transient"
