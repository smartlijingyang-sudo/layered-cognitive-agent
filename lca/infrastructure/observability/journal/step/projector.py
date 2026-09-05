"""JournalDocumentWriter:JournalDocument → ``journal.json`` 落盘。

ADR-0167 D11: spine ledger 是唯一 SSOT;``journal.json`` 是可重
建物化视图,由 :class:`StepTreeFoldDeriver` 在 flush 时 fold 事件后落盘。本
模块只负责写盘逻辑 + 序列化 dataclass,deriver 不再自己写文件。

为什么独立成 module:
    - 测试可单独针对"JournalDocument 落盘"行为做 round-trip。
    - deriver 与 reader 共享同一序列化规则。
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal_doc import JournalDocument
from lca.infrastructure.atomic_write import atomic_write_text


def to_jsonable(obj: Any) -> Any:
    """递归把 dataclass / tuple 转 dict / list(jsonable)。"""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return repr(obj)


class JournalDocumentWriter:
    """JournalDocument → ``journal.json``(原子写)。

    参数:
        output_path: 落盘文件路径,默认 ``traces/runs/<run_id>/journal.json``。
        indent: pretty-print 缩进,默认 2(便于 git diff / 人读)。
    """

    def __init__(
        self,
        output_path: str | Path,
        *,
        indent: int = 2,
    ) -> None:
        self._path = Path(output_path)
        self._indent = indent

    @property
    def output_path(self) -> Path:
        return self._path

    def write(self, document: JournalDocument) -> Path:
        """原子覆盖写 journal.json。"""
        if document.schema not in {"lca.journal/3", "lca.journal/3.1"}:
            raise ValueError(
                f"JournalDocumentWriter.write: expected schema in "
                f"{{'lca.journal/3', 'lca.journal/3.1'}}, got {document.schema!r}"
            )
        text = json.dumps(
            to_jsonable(document),
            indent=self._indent,
            ensure_ascii=False,
        )
        return atomic_write_text(self._path, text)


__all__ = ["JournalDocumentWriter", "to_jsonable"]
