"""Scope 闭集（ADR-0074 §三 + ADR-0067 §三裁剪）。

ADR-0074 §三把 0067 7 scope 压缩到 5：``release / profile / agent /
run / turn / experiment / device``（invocation → turn 合并）。
本枚举是 LCA scope 闭集，新值需 ADR。

tracker §15.4 ADR-0074 V9 写 "8 个合法 scope" 含 invocation；v3.1
§1.1 列表 7 项不含 invocation。本枚举以 7 项为准（含 invocation），
与 ADR-0074 V9 表述保持一致。
"""

from __future__ import annotations

from enum import Enum


class Scope(str, Enum):
    """Scope 闭集（ADR-0074 §三 + tracker §15.3 + §15.4）。

    7 个合法 scope：scope 决定 plugin 生命周期、grant 衰减、event 可见性
    与 audit 边界。新增第 8 个 scope 需 ADR。

    - ``release`` —— 跨 release 的全局声明（如 base capability）
    - ``profile`` —— 单 profile 范围内（patch / bundle 粒度）
    - ``agent`` —— 单 agent（spec 粒度）
    - ``run`` —— 单 run（一次完整执行；plan 粒度）
    - ``turn`` —— 单 turn（一次模型交互 + tool call）
    - ``invocation`` —— 单 tool invocation（单次 effect 边界）
    - ``experiment`` —— 实验 scope（fake provider、creator staging）
    - ``device`` —— 设备 scope（host runtime 边界）

    .. note::

        ADR-0074 §三裁剪把 invocation 与 turn 合并到 5 scope 集合；
        但 ADR-0074 V9 LogicAddress 评分（§15.3）保留 8 项含 invocation。
        本枚举保留 invocation 字段，标记 ``alias_of = "turn"`` 提示作者
        倾向使用 turn。
    """

    RELEASE = "release"
    PROFILE = "profile"
    AGENT = "agent"
    RUN = "run"
    TURN = "turn"
    INVOCATION = "invocation"
    EXPERIMENT = "experiment"
    DEVICE = "device"


SCOPE_ALIAS: dict[Scope, Scope | None] = {
    Scope.RELEASE: None,
    Scope.PROFILE: None,
    Scope.AGENT: None,
    Scope.RUN: None,
    Scope.TURN: None,
    Scope.INVOCATION: Scope.TURN,  # ADR-0074 §三裁剪动议
    Scope.EXPERIMENT: None,
    Scope.DEVICE: None,
}
"""scope 别名映射：``invocation → turn``（ADR-0074 §三裁剪）。"""


def parse_scope(value: object) -> Scope:
    """字符串 / 枚举 → Scope。值未匹配 → ``ValueError``。"""
    if isinstance(value, Scope):
        return value
    if isinstance(value, str):
        try:
            return Scope(value)
        except ValueError as exc:
            raise ValueError(f"unknown scope {value!r}; valid: {[s.value for s in Scope]}") from exc
    raise TypeError(f"scope must be str or Scope, got {type(value).__name__}")


def canonical_scope(scope: Scope) -> Scope:
    """返回 scope 的规范形式（沿 SCOPE_ALIAS 折叠别名）。"""
    return SCOPE_ALIAS.get(scope, scope) or scope


def all_scope_values() -> tuple[str, ...]:
    """全部 scope 字符串值（顺序确定）。"""
    return tuple(s.value for s in Scope)


__all__ = [
    "SCOPE_ALIAS",
    "Scope",
    "all_scope_values",
    "canonical_scope",
    "parse_scope",
]
