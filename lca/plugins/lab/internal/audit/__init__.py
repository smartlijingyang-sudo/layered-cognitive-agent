"""Load-time audit for stage worker modules.

ADR-0211 §8 落地切片:把 worker 体检从 ADR plan 落到可执行模块。

职责(单一):
    接收 ``module_path`` + 已反射出的 ``worker_fn``,返回体检错误清单;
    模块本身**不** raise,只产错误列表 —— 调用方(``hooks.discover_worker``)
    决定是 raise 还是 warning。

模块边界:
    signature_rules  W-1 ~ W-6   inspect.signature 体检
    body_rules       W-7 ~ W-10  ast 体检(函数体防御代码 / try-except)
    errors           WorkerAuditError / WorkerAuditFailure 类型
    reporter         错误展示形态(人类可读 / JSON / IDE-friendly)

不依赖:
    不 import hooks / loader / cordis,只读 inspect + ast + pathlib;
    自身可独立单测。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lca.plugins.lab.internal.audit import body_rules, signature_rules
from lca.plugins.lab.internal.audit.errors import (
    WorkerAuditError,
    WorkerAuditFailure,
)


def _resolve_location(worker_fn: Any, module_path: str) -> str:
    """把 worker_fn 解析到 ``<rel_path>:<lineno>`` 字符串,失败时回退到模块路径。"""
    try:
        import inspect

        src_file = inspect.getsourcefile(worker_fn) or ""
        _, lineno = inspect.getsourcelines(worker_fn)
    except (OSError, TypeError):
        return module_path
    # 拒绝非真实文件路径(虚拟 module、REPL、test scratch module):
    # 这些通常以 ``<`` 开头,不参与 relative_to。
    if src_file and not src_file.startswith("<"):
        try:
            rel = Path(src_file).resolve().relative_to(Path.cwd())
            return f"{rel}:{lineno}"
        except (ValueError, OSError):
            return f"{src_file}:{lineno}"
    return module_path


def audit_worker(module_path: str, worker_fn: Any) -> list[WorkerAuditError]:
    """对单个 worker_fn 跑全量体检,返回错误清单(空 = 通过)。

    不 raise;调用方按语义选择 raise 或 warn。
    """
    import inspect

    if not callable(worker_fn):
        return [
            WorkerAuditError(
                rule_id="W-0",
                location=module_path,
                message=f"object is not callable: {worker_fn!r}",
            )
        ]
    try:
        sig = inspect.signature(worker_fn)
        src = inspect.getsource(worker_fn)
    except (OSError, TypeError) as exc:
        return [
            WorkerAuditError(
                rule_id="W-0",
                location=module_path,
                message=f"cannot introspect worker_fn: {exc}",
            )
        ]

    location = _resolve_location(worker_fn, module_path)
    errs: list[WorkerAuditError] = []
    errs.extend(signature_rules.run(sig, location))
    errs.extend(body_rules.run(src, location))
    return errs


__all__ = [
    "WorkerAuditError",
    "WorkerAuditFailure",
    "audit_worker",
]
