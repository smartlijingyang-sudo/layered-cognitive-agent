"""DelegationResult —— 委派结算的一等类型化表示。

背景：成员返回曾以 ``TOOL_RESULT: {payload}`` 字符串糊进 working memory，
丢失归属（谁 / 哪个子任务 / 哪一步 / 成败），导致监督者把已返回的委派结果
误判为"历史记录"而重复委派。

本模块提供：
- ``DelegationResult``：一次委派的结算产物，团队 awareness 账本
  （``TeamAwareness.results``）的元素；
- ``find_result``：幂等键 ``(target_role, subtask)`` 的纯查询函数。

contracts 放纯函数的先例：``lca/contracts/role_status_rules.py``。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DelegationResult:
    """一次委派的结算产物 —— 监督控制面的一等事实。

    - ``TeamAwareness.results`` 是 lead prompt 与幂等委派的权威事实源
    - 失败结算同样入账（供 prompt 暴露"谁没答成"），但 ``find_result``
      只命中成功结果 —— 失败可以被重新委派
    """

    result_id: str
    target_role: str
    subtask: str
    output: str | None
    success: bool
    error: str | None
    task_id: str | None
    step: int
    returned_at: datetime


def find_result(
    results: Sequence[DelegationResult], *, target_role: str, subtask: str
) -> DelegationResult | None:
    """幂等查询：精确匹配 ``(target_role, subtask)`` 的成功结果。

    刻意保守 —— 只拦字面重复；改写措辞的新问题不受影响。
    """
    for item in results:
        if item.success and item.target_role == target_role and item.subtask == subtask:
            return item
    return None
