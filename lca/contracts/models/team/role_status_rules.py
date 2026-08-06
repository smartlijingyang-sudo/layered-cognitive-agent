"""RoleStatus 的语义分类——terminal(终态) vs done(成功终态)的唯一权威定义。

任何需要判断"某个 RoleStatus 是否终态 / 是否成功终态"的地方,一律引用本文件的
函数,禁止在别处用 ``== RoleStatus.DONE`` / ``!= RoleStatus.DONE`` 重新发明判定逻辑。
这是问题 A(终态/成功终态混淆)不再复发的架构保证:分类逻辑只存在一份。

契约层合规:本文件只有模块级纯函数,不含类/方法,不受 ADR-0015
"非 Protocol 类须为 dataclass 且无自定义方法"约束——该约束只管类,不管自由函数。
与 ``contracts/semantic_keys.py``(对 failure_kind 字符串值的语义解释)是同一模式。
"""

from __future__ import annotations

from lca.contracts.atoms.enums import RoleStatus

_TERMINAL_STATUSES: frozenset[RoleStatus] = frozenset({RoleStatus.DONE, RoleStatus.FAILED})


def is_terminal_status(status: RoleStatus) -> bool:
    """是否已到终态(terminal)——状态机不会再处理它,不代表成功。"""
    return status in _TERMINAL_STATUSES


def is_success_status(status: RoleStatus) -> bool:
    """是否成功终态(done)。"""
    return status == RoleStatus.DONE
