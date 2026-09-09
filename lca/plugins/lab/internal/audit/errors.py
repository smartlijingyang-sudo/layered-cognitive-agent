"""Audit module 公共类型。

独立文件,避免与 rules / __init__ 循环 import。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkerAuditError:
    """单条体检错误。

    rule_id: W-1 .. W-10(对应 ADR-0211 §1.1 / §1.3 / §0.2)
    location: 函数源文件相对路径:行号(供 IDE 跳转)
    message: 人类可读描述
    """

    rule_id: str
    location: str
    message: str

    def format(self) -> str:
        return f"{self.location}: [{self.rule_id}] {self.message}"


class WorkerAuditFailure(Exception):
    """体检失败的聚合异常。

    load_all() 收到此异常时按 ADR-0211 §8 fail-loud 语义直接 raise,
    不允许降级到 WARNING(降级会让 worker 错误潜伏到 invoke 阶段)。
    """

    def __init__(self, errors: list[WorkerAuditError], *, module_path: str) -> None:
        self.errors = tuple(errors)
        self.module_path = module_path
        bullets = "\n".join(f"  - {e.format()}" for e in self.errors)
        super().__init__(
            f"{module_path}: {len(self.errors)} worker audit error(s):\n{bullets}"
        )


__all__ = ["WorkerAuditError", "WorkerAuditFailure"]