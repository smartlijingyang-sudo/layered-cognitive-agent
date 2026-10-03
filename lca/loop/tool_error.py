"""Loop-layer tool error recovery: classification, retry budget, failure explanation.

docs/specs/tool-failure-recovery.md §7 的基本规则::

    USE_TOOL + failed Observation → 继续（act.main → think.main）

前提是失败带 ``failure_kind`` 分类（``act.observe.terminate_decide`` 只在
``failure_kind is None`` 时终止）。本模块提供：

- 确定性错误分型（可恢复 vs 致命），不调 LLM；
- 可配置的连续失败预算（默认 3 次）；
- run 真失败时的中文用户可读解释（say-do 场景感知：模型承诺过
  行动却没做到时，解释要承认这一点，而不是静默死）；
- visit 扫描 helpers：从 interpreter visits 里找 terminal tool error
  并计数连续失败（供 driver 决策）。

fail-closed 方向：分型未知默认可恢复（有预算兜底，不会无限重试）；
认证/权限类一律致命（绝不盲目重试）。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ToolErrorKind(StrEnum):
    """工具错误的恢复语义。"""

    RECOVERABLE = "recoverable"
    """可恢复：模型换参/换方案后可重试（参数校验、未知命名空间、超时等）。"""

    FATAL = "fatal"
    """致命：重试无意义（认证失效、权限拒绝），应直接终止并解释。"""


# 致命模式优先匹配（fail-closed）：认证/权限问题绝不盲目重试。
_FATAL_PATTERNS: tuple[str, ...] = (
    "unauthorized",
    "unauthenticated",
    "401",
    "forbidden",
    "403",
    "permission denied",
    "权限不足",
    "无权限",
    "session expired",
    "会话过期",
    "会话失效",
    "登录失效",
    "登录过期",
    "token expired",
    "invalid token",
    "token 无效",
    "auth failed",
    "认证失败",
    "鉴权失败",
)


def classify_tool_error(error_text: str | None) -> ToolErrorKind:
    """确定性分型。致命模式优先；未知默认可恢复（预算兜底）。"""
    text = (error_text or "").lower()
    if any(p in text for p in _FATAL_PATTERNS):
        return ToolErrorKind.FATAL
    return ToolErrorKind.RECOVERABLE


@dataclass
class ToolErrorBudget:
    """连续可恢复失败的预算。默认 3 次，可配置。

    语义：模型对"同类"可恢复错误最多重规划 ``max_recoverable_retries``
    次；第 ``max_recoverable_retries + 1`` 次连续失败时 run 终止。
    成功一次即清零（非连续不累计）。
    """

    max_recoverable_retries: int = 3
    consecutive_failures: int = 0

    def note_recoverable_failure(self) -> bool:
        """记录一次可恢复失败。返回 True 表示预算内、可继续 replan。"""
        self.consecutive_failures += 1
        return self.consecutive_failures <= self.max_recoverable_retries

    def note_success(self) -> None:
        """成功一次，清零连续计数。"""
        self.consecutive_failures = 0

    @property
    def exhausted(self) -> bool:
        """预算是否已耗尽（已超过最大重试次数）。"""
        return self.consecutive_failures > self.max_recoverable_retries


def build_failure_explanation(
    *,
    tool_name: str | None,
    error_text: str | None,
    attempts: int,
    kind: ToolErrorKind,
) -> str:
    """run 真失败时的中文用户可读解释，保证非空。

    say-do 感知：如模型曾承诺行动（如"让我先加载 OA 工具"）却失败，
    解释承认"尝试过但没做到"，而不是静默消失。
    """
    tool = tool_name or "工具"
    err = (error_text or "未知错误").strip().replace("\n", " ")
    if len(err) > 180:
        err = err[:180] + "…"
    if kind is ToolErrorKind.FATAL:
        return (
            f"抱歉，我在调用{tool}时遇到了权限或认证问题（{err}），"
            f"无法继续执行。请检查登录状态或权限配置后，再让我重试。"
        )
    if attempts > 1:
        return (
            f"抱歉，我刚才尝试调用{tool}来帮你处理，但遇到了问题（{err}），"
            f"换了 {attempts} 种方式仍未成功。建议你换个说法再试一次，"
            f"或稍后再试。"
        )
    return (
        f"抱歉，我刚才尝试调用{tool}来帮你处理，但遇到了问题（{err}）。"
        f"建议你换个说法再试一次，或稍后再试。"
    )


def _as_tool_record(
    key: Any, value: Any
) -> tuple[str | None, bool | None, str | None] | None:
    """把 outputs 条目归一化为 ``(tool_name, success, error)``，或 None。"""
    # Observation-like 对象
    success = getattr(value, "success", None)
    if isinstance(success, bool):
        tool_name = getattr(value, "tool_name", None)
        if tool_name is None and isinstance(key, str):
            tool_name = key
        error = getattr(value, "error", None)
        return (
            str(tool_name) if tool_name else None,
            success,
            str(error) if error else None,
        )
    # Dict 形态
    if isinstance(value, dict):
        success = value.get("success")
        if isinstance(success, bool):
            tool_name = value.get("tool_name") or (key if isinstance(key, str) else None)
            error = value.get("error")
            return (
                str(tool_name) if tool_name else None,
                success,
                str(error) if error else None,
            )
    return None


def _iter_tool_observations(visits: Any) -> Iterator[tuple[str | None, bool | None, str | None]]:
    """从 visits 里按新→旧产出 ``(tool_name, success, error)``。防御式：永不抛异常。"""
    try:
        ordered = list(visits or ())
    except TypeError:
        return
    for visit in reversed(ordered):
        outputs = getattr(visit, "outputs", None)
        if not isinstance(outputs, dict):
            continue
        for key, value in outputs.items():
            try:
                record = _as_tool_record(key, value)
            except Exception:
                continue
            if record is not None:
                yield record


def find_terminal_tool_error(visits: Any) -> tuple[str | None, str | None]:
    """最近的失败 tool observation：``(tool_name, error_text)``，无则 ``(None, None)``。"""
    for tool_name, success, error_text in _iter_tool_observations(visits):
        if success is False:
            return (tool_name, error_text)
    return (None, None)


def count_consecutive_tool_failures(visits: Any, tool_name: str | None) -> int:
    """按新→旧数 ``tool_name`` 的连续失败数。遇到成功或别的工具即停。"""
    count = 0
    for name, success, _ in _iter_tool_observations(visits):
        if success is True:
            break
        if success is False:
            if tool_name is not None and name != tool_name:
                break
            count += 1
    return count


__all__ = [
    "ToolErrorKind",
    "ToolErrorBudget",
    "build_failure_explanation",
    "classify_tool_error",
    "count_consecutive_tool_failures",
    "find_terminal_tool_error",
]
