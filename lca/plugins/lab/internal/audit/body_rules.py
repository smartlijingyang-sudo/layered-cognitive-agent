"""AST-level audit rules (W-7 ~ W-10).

ADR-0211 §1.3 / §0.2 命题 5 强约束的函数体视角。

W-7: Worker.execute 不写 try/except(framework 收错误)
W-8: Worker.execute 不折 receipt / EXCEPTION
W-9: register_worker / Seams / body_provider.get_body 三件不出现
W-10: Worker.execute 不写 if x is None / getattr 兜底

实现策略:
    ast.parse(src) 后 walk AST;不报 false-positive 是优先级 —— 默认拒绝
    "Worker 自己写 try/except" 模式;特定白名单模式(如 typed guard)
    留给后续 review。
"""
from __future__ import annotations

import ast
from typing import Iterable

from lca.plugins.lab.internal.audit.errors import WorkerAuditError


# W-9: framework 退役符号(ADR-0211 §1.4)与 import 路径
_FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "register_worker",
    "Seams",
    "body_provider",
    "get_body",
})


def _w7_no_try_except(tree: ast.AST, loc: str) -> list[WorkerAuditError]:
    errs: list[WorkerAuditError] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            errs.append(
                WorkerAuditError(
                    "W-7",
                    loc,
                    "Worker.execute 出现 try/except;framework 按 Config.on_error 收错误,Worker 不写",
                )
            )
    return errs


def _w8_no_receipt_construction(tree: ast.AST, loc: str) -> list[WorkerAuditError]:
    """检测 Worker 自己构造 Receipt / EXCEPTION 类(模式:``Receipt(...)`` / ``EXCEPTION(...)``)。"""
    errs: list[WorkerAuditError] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name: str | None = None
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in {"Receipt", "EXCEPTION", "ErrorReceipt"}:
            errs.append(
                WorkerAuditError(
                    "W-8",
                    loc,
                    f"Worker 构造 {name}(...) ;framework 收口 receipt,Worker 不折",
                )
            )
    return errs


def _w9_no_retired_symbols(tree: ast.AST, loc: str) -> list[WorkerAuditError]:
    errs: list[WorkerAuditError] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            errs.append(
                WorkerAuditError(
                    "W-9",
                    loc,
                    f"引用退役符号 {node.id!r};ADR-0211 §1.4 退役清单不留跨 PR 后门",
                )
            )
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_NAMES:
            errs.append(
                WorkerAuditError(
                    "W-9",
                    loc,
                    f"属性访问 {node.attr!r} 在退役清单;改用 typed 路径",
                )
            )
    return errs


def _w10_no_defensive_guards(tree: ast.AST, loc: str) -> list[WorkerAuditError]:
    """检测 Worker 写 ``if x is None: ...`` / ``getattr(x, ..., default)`` 防御。
    例外:对 typed dataclass 做 ``is None`` 是允许的(framework 投影后仍 typed),
    此处保守地只检 *任一* ``is None`` 比较 + ``getattr(...)`` 调用,避免漏报;
    误报留给 review。
    """
    errs: list[WorkerAuditError] = []
    for node in ast.walk(tree):
        # `x is None` / `x is not None`
        if isinstance(node, ast.Compare):
            for comp in node.comparators:
                if isinstance(comp, ast.Constant) and comp.value is None:
                    errs.append(
                        WorkerAuditError(
                            "W-10",
                            loc,
                            "Worker.execute 写 `x is None` 兜底;framework fail-loud,Worker 不感知层级",
                        )
                    )
                    break
        # `getattr(x, attr, default)` 三参形式
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "getattr":
                if len(node.args) >= 3:
                    errs.append(
                        WorkerAuditError(
                            "W-10",
                            loc,
                            "Worker.execute 用 `getattr(x, attr, default)` 兜底;fail-loud",
                        )
                    )
    return errs


def run(src: str, location: str) -> list[WorkerAuditError]:
    """跑全部 body 规则;返回错误清单(空 = 通过)。"""
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [
            WorkerAuditError(
                "W-0",
                location,
                f"worker_fn source 解析失败: {exc}",
            )
        ]
    errs: list[WorkerAuditError] = []
    errs.extend(_w7_no_try_except(tree, location))
    errs.extend(_w8_no_receipt_construction(tree, location))
    errs.extend(_w9_no_retired_symbols(tree, location))
    errs.extend(_w10_no_defensive_guards(tree, location))
    return errs


__all__ = ["run"]