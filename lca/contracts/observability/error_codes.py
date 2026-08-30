"""ErrorCode 字典 —— ADR-0065 §六 / PR-9 / ADR-0064 §9 收尾。

10 大类 ~30 稳定码(0065 显式要求 closed-set);``lca-ops diagnose <alias>``
据此处给出可执行修复建议。新增 code 必须 ADR 评审。
"""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    """错误大类。"""

    LLM = "llm"
    TOOL = "tool"
    GATE = "gate"
    LOOP = "loop"
    PLUGIN = "plugin"
    MEMORY = "memory"
    SANDBOX = "sandbox"
    NETWORK = "network"
    AUTH = "auth"
    USER = "user"


class ErrorCode(str, Enum):
    """稳定错误码(0065 §六 + 0064 §9 收尾)。"""

    # LLM
    LLM_RATE_LIMIT = "llm_rate_limit"
    LLM_CONTEXT_OVERFLOW = "llm_context_overflow"
    LLM_CONTENT_BLOCKED = "llm_content_blocked"
    LLM_MODEL_NOT_FOUND = "llm_model_not_found"
    # TOOL
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_PERMISSION_DENIED = "tool_permission_denied"
    TOOL_INVALID_ARGUMENT = "tool_invalid_argument"
    TOOL_NOT_FOUND = "tool_not_found"
    # GATE
    GATE_DENIED = "gate_denied"
    GATE_REWRITTEN = "gate_rewritten"
    # LOOP
    LOOP_STUCK = "loop_stuck"
    LOOP_OSCILLATING = "loop_oscillating"
    LOOP_MAX_STEPS = "loop_max_steps"
    # PLUGIN
    PLUGIN_BOOT_FAILED = "plugin_boot_failed"
    PLUGIN_MISSING_DEPENDENCY = "plugin_missing_dependency"
    # MEMORY
    MEMORY_POISONED = "memory_poisoned"
    MEMORY_FULL = "memory_full"
    # SANDBOX
    SANDBOX_OFFLINE = "sandbox_offline"
    SANDBOX_IO_ERROR = "sandbox_io_error"
    # NETWORK
    NETWORK_TIMEOUT = "network_timeout"
    NETWORK_DNS = "network_dns"
    # AUTH
    AUTH_EXPIRED = "auth_expired"
    AUTH_INSUFFICIENT = "auth_insufficient"
    # USER
    USER_CANCELLED = "user_cancelled"
    USER_ABANDONED = "user_abandoned"


# ErrorCategory → ErrorCode 映射(防止 category 与 code 漂移)
_CATEGORY_TO_CODES: dict[ErrorCategory, tuple[ErrorCode, ...]] = {
    ErrorCategory.LLM: (
        ErrorCode.LLM_RATE_LIMIT,
        ErrorCode.LLM_CONTEXT_OVERFLOW,
        ErrorCode.LLM_CONTENT_BLOCKED,
        ErrorCode.LLM_MODEL_NOT_FOUND,
    ),
    ErrorCategory.TOOL: (
        ErrorCode.TOOL_TIMEOUT,
        ErrorCode.TOOL_PERMISSION_DENIED,
        ErrorCode.TOOL_INVALID_ARGUMENT,
        ErrorCode.TOOL_NOT_FOUND,
    ),
    ErrorCategory.GATE: (ErrorCode.GATE_DENIED, ErrorCode.GATE_REWRITTEN),
    ErrorCategory.LOOP: (
        ErrorCode.LOOP_STUCK,
        ErrorCode.LOOP_OSCILLATING,
        ErrorCode.LOOP_MAX_STEPS,
    ),
    ErrorCategory.PLUGIN: (
        ErrorCode.PLUGIN_BOOT_FAILED,
        ErrorCode.PLUGIN_MISSING_DEPENDENCY,
    ),
    ErrorCategory.MEMORY: (ErrorCode.MEMORY_POISONED, ErrorCode.MEMORY_FULL),
    ErrorCategory.SANDBOX: (
        ErrorCode.SANDBOX_OFFLINE,
        ErrorCode.SANDBOX_IO_ERROR,
    ),
    ErrorCategory.NETWORK: (ErrorCode.NETWORK_TIMEOUT, ErrorCode.NETWORK_DNS),
    ErrorCategory.AUTH: (ErrorCode.AUTH_EXPIRED, ErrorCode.AUTH_INSUFFICIENT),
    ErrorCategory.USER: (ErrorCode.USER_CANCELLED, ErrorCode.USER_ABANDONED),
}


def category_of(code: ErrorCode) -> ErrorCategory:
    """code → category(线性扫描;~30 码 O(30) 常数时间)。"""
    for cat, codes in _CATEGORY_TO_CODES.items():
        if code in codes:
            return cat
    raise ValueError(f"ErrorCode {code!r} not in any category")


# 内置 diagnose alias + 修复建议(0064 §9 起步)
DIAGNOSE_ALIASES: dict[str, tuple[ErrorCode, ...]] = {
    "model_not_seen": (
        ErrorCode.LLM_MODEL_NOT_FOUND,
        ErrorCode.PLUGIN_BOOT_FAILED,
    ),
    "loop_stuck": (
        ErrorCode.LOOP_STUCK,
        ErrorCode.LOOP_OSCILLATING,
        ErrorCode.LOOP_MAX_STEPS,
    ),
    "memory_poisoned": (
        ErrorCode.MEMORY_POISONED,
        ErrorCode.MEMORY_FULL,
    ),
    "approval_rejected": (
        ErrorCode.GATE_DENIED,
        ErrorCode.TOOL_PERMISSION_DENIED,
        ErrorCode.AUTH_INSUFFICIENT,
    ),
}


DIAGNOSE_HINTS: dict[str, str] = {
    "model_not_seen": ("检查 llm_resolver 配置;确认 LLM_API_KEY 已设置且 model 名称拼写正确。"),
    "loop_stuck": ("检查 step 数与 oscillation 模式;增大 max_steps 或调整 reasoner prompt。"),
    "memory_poisoned": (
        "清空 memory_layer 缓存或调整 ingest policy;检查 memory.commit 是否被反复回滚。"
    ),
    "approval_rejected": ("检查 tool capability_grant 与 user role;查看 audit log 确认拒绝原因。"),
}


__all__ = [
    "DIAGNOSE_ALIASES",
    "DIAGNOSE_HINTS",
    "ErrorCategory",
    "ErrorCode",
    "category_of",
]
