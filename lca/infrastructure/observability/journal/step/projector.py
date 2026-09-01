"""StepGroupedProjector —— JournalDocument 一次性落盘投影(ADR-0164 草案)。

对比 JsonlJournalProjector:
    - **不再流式追加**。 完整 JournalDocument 在 close_document 时一次性
      序列化, 写到 ``journal.json``。
    - **不需要 enricher / sidecar / _delta_buffers**。 step-tree 本身
      是结构化的(thinking / tool_call / tool_result / spans 已归一),
      不需要 run-time 注入摘要或截断。
    - **不写 narrative.md**。 Phase 4 由 StepNarrativeWriter 接管。

落盘时机:
    projector 不主动轮询 step_lifecycle。 调用方在 close_document 之后
    调 ``projector.write(document)``。 详见 ``StepGroupedBackend``。

原子性: 写 ``journal.json.tmp`` + ``Path.replace`` 落盘, 进程崩溃不会
留半截文件。
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from lca.contracts.models.observability.journal_doc import JournalDocument


def _to_jsonable(obj: Any) -> Any:
    """递归把 dataclass / tuple 转 dict / list(jsonable)。

    JournalDocument / JournalStep / 各原语都是 frozen dataclass, 直接
    ``asdict()`` 能展开。 tuple → list 是 json 的硬性要求。
    """
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    # 兜底: repr(用于 Enum / 特殊对象)。 JournalDocument 路径不会出现非
    # jsonable, 此处只为防御。
    return repr(obj)


class StepGroupedProjector:
    """step-tree 投影器 —— 把 JournalDocument 落盘到 ``journal.json``。

    参数:
        output_path: 落盘文件路径, 默认 ``traces/runs/<run_id>/journal.json``。
        indent: pretty-print 缩进, 默认 2(便于 git diff / 人读)。
        ensure_parents: 写之前 mkdir -p 父目录。
    """

    def __init__(
        self,
        output_path: str | Path,
        *,
        indent: int = 2,
        ensure_parents: bool = True,
    ) -> None:
        self._path = Path(output_path)
        if ensure_parents:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        self._indent = indent

    @property
    def output_path(self) -> Path:
        """落盘目标(用于 boot 装配校验)。"""
        return self._path

    def write(self, document: JournalDocument) -> Path:
        """写 JournalDocument 到 ``journal.json``(原子覆盖)。

        返回: 写完的文件路径(便于调用方校验)。
        异常: schema 不对 / 序列化失败 → 直接抛, 不写半截。
        """
        if document.schema != "lca.journal/3":
            raise ValueError(
                f"StepGroupedProjector.write: expected schema='lca.journal/3', "
                f"got {document.schema!r}"
            )
        payload = _to_jsonable(document)
        text = json.dumps(payload, indent=self._indent, ensure_ascii=False)
        # 原子写: tmp → rename
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(self._path.parent),
            prefix=self._path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as fh:
            fh.write(text)
            tmp_path = Path(fh.name)
        try:
            tmp_path.replace(self._path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        return self._path


__all__ = ["StepGroupedProjector"]
