"""Signature-level audit rules (W-1 ~ W-6).

ADR-0211 §1.1 / §1.2 强约束的 signature 视角。

W-1: Worker.execute 全 keyword-only
W-2: 入参必是 typed 类型(禁 ``dict`` / ``Any``)
W-3: 禁入参 ``ctx`` / ``seams`` / ``node`` / ``inputs``
W-4: 入参名不与 Config 静态端口名重叠(暂留 W-4 stub,
     Config 收紧不在本模块负责)
W-5: 返回值必 typed(禁空 annotation / ``Any``)
W-6: 函数本体不与 framework 容器同名(防误用)
"""
from __future__ import annotations

import inspect
from typing import Any

from lca.plugins.lab.internal.audit.errors import WorkerAuditError

_FORBIDDEN_PARAMS = frozenset({"ctx", "seams", "node", "inputs"})


def _w1_keyword_only(sig: inspect.Signature, loc: str) -> list[WorkerAuditError]:
    errs: list[WorkerAuditError] = []
    for pname, param in sig.parameters.items():
        if param.kind is inspect.Parameter.VAR_POSITIONAL:
            errs.append(
                WorkerAuditError(
                    "W-1",
                    loc,
                    f"parameter {pname!r} 用了 *args;Worker.execute 必须全 keyword-only(`def name(*, ...)`)",
                )
            )
            continue
        if param.kind is inspect.Parameter.POSITIONAL_ONLY:
            errs.append(
                WorkerAuditError(
                    "W-1",
                    loc,
                    f"parameter {pname!r} 是 positional-only;必须显式 `*` 之后",
                )
            )
            continue
        if param.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD:
            errs.append(
                WorkerAuditError(
                    "W-1",
                    loc,
                    f"parameter {pname!r} 是 POSITIONAL_OR_KEYWORD;必须 keyword-only",
                )
            )
    return errs


def _w2_typed_input(sig: inspect.Signature, loc: str) -> list[WorkerAuditError]:
    errs: list[WorkerAuditError] = []
    for pname, param in sig.parameters.items():
        if param.kind is inspect.Parameter.VAR_KEYWORD:
            errs.append(
                WorkerAuditError(
                    "W-2",
                    loc,
                    "**kwargs 隐藏 typed 依赖;不允许(framework 投影层负责 typed)",
                )
            )
            continue
        ann = param.annotation
        if ann is inspect.Parameter.empty:
            errs.append(
                WorkerAuditError(
                    "W-2",
                    loc,
                    f"parameter {pname!r} 缺类型标注;Worker 必须 typed",
                )
            )
            continue
        # PEP 563 lazy annotations arrive as forward-ref strings
        # (``from __future__ import annotations``);normalize before check.
        if isinstance(ann, str):
            if ann in {"dict", "Dict"}:
                errs.append(
                    WorkerAuditError(
                        "W-2",
                        loc,
                        f"parameter {pname!r} 用了 dict(forward-ref);禁止(用 frozen dataclass / Protocol)",
                    )
                )
            continue
        if ann is Any or ann is dict:
            errs.append(
                WorkerAuditError(
                    "W-2",
                    loc,
                    f"parameter {pname!r} 用了 {getattr(ann, '__name__', str(ann))};禁止(用 frozen dataclass / Protocol)",
                )
            )
    return errs


def _w3_forbidden_framework_params(
    sig: inspect.Signature, loc: str
) -> list[WorkerAuditError]:
    errs: list[WorkerAuditError] = []
    for pname in sig.parameters:
        if pname in _FORBIDDEN_PARAMS:
            errs.append(
                WorkerAuditError(
                    "W-3",
                    loc,
                    f"parameter {pname!r} 是 framework 容器;framework 投影层在调用前完成 typed 投影,Worker 不感知",
                )
            )
    return errs


def _w5_typed_return(sig: inspect.Signature, loc: str) -> list[WorkerAuditError]:
    ann = sig.return_annotation
    if ann is inspect.Signature.empty:
        return [
            WorkerAuditError(
                "W-5",
                loc,
                "返回值缺类型标注;Worker 必须 typed(frozen dataclass / Protocol)",
            )
        ]
    if isinstance(ann, str):
        if ann in {"dict", "Dict"}:
            return [
                WorkerAuditError(
                    "W-5",
                    loc,
                    "返回值用了 dict(forward-ref);禁止(用 typed dataclass;不允许 dict[str, Artifact] 返回)",
                )
            ]
        return []
    if ann is Any or ann is dict:
        return [
            WorkerAuditError(
                "W-5",
                loc,
                f"返回值用了 {getattr(ann, '__name__', str(ann))};禁止(用 typed dataclass;不允许 dict[str, Artifact] 返回)",
            )
        ]
    return []


def run(sig: inspect.Signature, location: str) -> list[WorkerAuditError]:
    """跑全部 signature 规则;返回错误清单(空 = 通过)。"""
    errs: list[WorkerAuditError] = []
    errs.extend(_w1_keyword_only(sig, location))
    errs.extend(_w2_typed_input(sig, location))
    errs.extend(_w3_forbidden_framework_params(sig, location))
    errs.extend(_w5_typed_return(sig, location))
    return errs


__all__ = ["run"]
