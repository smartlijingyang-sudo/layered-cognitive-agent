"""Tool failure degradation layer (ADR-0267).

muse principle: Tool failure is data, not a crash.
A tool error becomes a structured result the agent reasons about,
not an exception that kills the run.

Degradation policy by failure kind:
- PERMISSION (403, auth): Convert to user-actionable guidance. The run
  continues; the agent informs the user what to fix.
- TRANSIENT (retries exhausted): Mark degraded, suggest retry later.
- DETERMINISTIC: Fail the specific action, not necessarily the run.
  The agent decides if it's on the critical path.
- NOT_FOUND: Resource doesn't exist. Agent decides: create, skip, or ask.

The key invariant: a single tool failure NEVER directly fails a run.
The agent always gets a chance to degrade gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DegradationKind(str, Enum):
    """Classification of tool failures for degradation purposes."""

    PERMISSION = "permission"  # 403, auth, insufficient permissions
    TRANSIENT = "transient"  # Retries exhausted, may succeed later
    DETERMINISTIC = "deterministic"  # Will fail every time, don't retry
    NOT_FOUND = "not_found"  # Resource doesn't exist


@dataclass(frozen=True)
class DegradedResult:
    """A tool failure converted to agent-actionable data.

    Instead of raising, the executor returns this. The agent's
    decision loop sees a structured failure it can reason about:
    retry with different args, try an alternative tool, or
    inform the user with specific guidance.
    """

    tool_name: str
    kind: DegradationKind
    # Human-readable summary for the agent to act on
    summary: str
    # Specific guidance for the user (if user action can fix it)
    user_guidance: str | None = None
    # Original error for debugging
    original_error: str | None = None
    # Whether the agent should consider this terminal for its current goal
    # (None = agent decides based on context)
    terminal_hint: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return False


def classify_error(error_message: str, status_code: int | None = None) -> DegradationKind:
    """Classify a tool error into a degradation kind.

    muse principle: Classification must be precise where possible.
    Permission errors are precisely identifiable (403, auth keywords).
    """
    msg_lower = error_message.lower()

    # Permission errors: precisely identifiable
    if status_code == 403 or status_code == 401:
        return DegradationKind.PERMISSION
    permission_markers = [
        "permission",
        "unauthorized",
        "forbidden",
        "insufficientpermissions",
        "api_key",
        "apikey",
        "auth_config",
        "access denied",
    ]
    if any(m in msg_lower for m in permission_markers):
        return DegradationKind.PERMISSION

    # Not found: precisely identifiable
    not_found_markers = ["not found", "404", "does not exist", "no such"]
    if status_code == 404 or any(m in msg_lower for m in not_found_markers):
        return DegradationKind.NOT_FOUND

    # Transient markers
    transient_markers = [
        "timeout",
        "timed out",
        "connection",
        "network",
        "temporary",
        "try again",
        "rate limit",
        "429",
        "503",
        "502",
    ]
    if any(m in msg_lower for m in transient_markers):
        return DegradationKind.TRANSIENT

    # Default: deterministic (fail-fast, don't retry blindly)
    return DegradationKind.DETERMINISTIC


def degrade(
    tool_name: str,
    error_message: str,
    status_code: int | None = None,
    invocation_id: str | None = None,
) -> DegradedResult:
    """Convert a tool failure into a DegradedResult.

    This is the single entry point. Call it instead of raising
    when a tool fails terminally. The run continues; the agent decides.
    """
    kind = classify_error(error_message, status_code)

    if kind == DegradationKind.PERMISSION:
        return DegradedResult(
            tool_name=tool_name,
            kind=kind,
            summary=f"工具 {tool_name} 权限不足，无法执行",
            user_guidance=(
                f"工具 {tool_name} 需要更高的权限。请检查 API key 或授权配置，"
                f"确保已授予所需权限后重试。具体错误：{error_message[:200]}"
            ),
            original_error=error_message,
            terminal_hint=False,  # User can fix this; not terminal
            extra={"invocation_id": invocation_id, "status_code": status_code},
        )

    if kind == DegradationKind.TRANSIENT:
        return DegradedResult(
            tool_name=tool_name,
            kind=kind,
            summary=f"工具 {tool_name} 暂时不可用（已重试）",
            user_guidance="服务暂时不可用，稍后重试可能成功。",
            original_error=error_message,
            terminal_hint=False,
            extra={"invocation_id": invocation_id},
        )

    if kind == DegradationKind.NOT_FOUND:
        return DegradedResult(
            tool_name=tool_name,
            kind=kind,
            summary=f"工具 {tool_name} 请求的资源不存在",
            user_guidance=None,  # Agent decides: create, skip, or ask
            original_error=error_message,
            terminal_hint=None,  # Agent decides based on context
            extra={"invocation_id": invocation_id},
        )

    # DETERMINISTIC
    return DegradedResult(
        tool_name=tool_name,
        kind=kind,
        summary=f"工具 {tool_name} 执行失败（确定性错误，重试无意义）",
        user_guidance=None,
        original_error=error_message,
        terminal_hint=None,
        extra={"invocation_id": invocation_id},
    )
