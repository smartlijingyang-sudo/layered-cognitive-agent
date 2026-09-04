"""SpineReader —— 事实链唯一读取入口 —— ADR-0183 §3.8 + I-FW-SSOT-1。

派生系统（ProjectionDeriver / StepTreeDeriver / ExporterHook）全部从 reader 派生。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from lca_kernel.events.spine_runtime import SpineEventRecord

log = logging.getLogger(__name__)


class SpineFileMissingError(FileNotFoundError):
    """SpineReader.locate 在 spine 文件不存在时抛错（fail-loud,非 silent zero）。

    PR-4 收口：reader 不再 silent fallback 到旧单文件 layout —— 该命名
    已退役,直接抛错让 caller 走诊断路径。
    """


class SpineReader:
    """事实链唯一读取入口（I-FW-SSOT-1）。

    所有派生系统（ProjectionDeriver / StepTreeDeriver / ExporterHook）必须从
    reader 派生；禁止直读 ``<run_id>.spine.jsonl`` 文件。

    三种使用形态:
    - :meth:`locate` —— 解析并校验 spine 物理路径
    - :meth:`events` —— 逐行反序列化为 :class:`SpineEventRecord`（typed reader）
    - :meth:`read_dicts` —— 逐行原样产出原始 dict（供旧 reader / deriver 用,
      旧 format 与新 format 都能消费;不再走旧单文件 layout 兜底）
    """

    def __init__(self, run_id: str, *, path: Path | None = None) -> None:
        self._run_id = run_id
        self._path = path or self._default_path(run_id)

    @staticmethod
    def _default_path(run_id: str) -> Path:
        """默认 spine 路径（<run_id>.spine.jsonl，相对 cwd）。

        本 PR 不绑 run_locator（PR-4 后续步骤），先返回相对路径。
        """
        return Path(f"{run_id}.spine.jsonl")

    @classmethod
    def locate(
        cls,
        run_id: str,
        *,
        root: Path | None = None,
    ) -> Path:
        """解析并校验 ``<run_id>.spine.jsonl`` 物理路径 —— PR-4 唯一 reader 入口。

        Args:
            run_id: 目标 run 标识。
            root: per-run 父目录（默认 cwd）。常见用法是
                ``FilesystemRunLocator(traces_root).run_dir(run_id)``。

        Returns:
            解析后的 spine 文件路径。

        Raises:
            SpineFileMissingError: spine 文件不存在（不向旧单文件 layout
                兜底 —— 该命名已退役,I-FW-SSOT-1 守护）。

        Contract:
        - 默认文件名 = ``<run_id>.spine.jsonl``（PR-27 L10 / ADR-0169）。
        - 不做 ``.exists()`` 二次校验 —— 抛错即失败,避免 silent zero。
        """
        parent = root if root is not None else Path.cwd()
        spine_path = parent / f"{run_id}.spine.jsonl"
        if not spine_path.exists():
            raise SpineFileMissingError(
                f"spine ledger not found: {spine_path} (run_id={run_id})"
            )
        return spine_path

    def events(self) -> Iterator[SpineEventRecord]:
        """逐行读 spine.jsonl，每行反序列化为 SpineEventRecord。

        损坏行（json.JSONDecodeError / 缺字段）：log + skip，不 raise。
        """
        if not self._path.exists():
            log.warning(
                "SpineReader: file missing",
                extra={"run_id": self._run_id, "path": str(self._path)},
            )
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, start=1):
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    log.warning(
                        "SpineReader: skip corrupted line",
                        extra={
                            "run_id": self._run_id,
                            "path": str(self._path),
                            "line_no": line_no,
                            "error": str(exc),
                        },
                    )
                    continue
                try:
                    yield SpineEventRecord.from_dict(data)
                except (KeyError, TypeError, ValueError) as exc:
                    log.warning(
                        "SpineReader: skip malformed record",
                        extra={
                            "run_id": self._run_id,
                            "path": str(self._path),
                            "line_no": line_no,
                            "error": str(exc),
                        },
                    )
                    continue

    def filter(self, *, category_prefix: str | None = None) -> Iterator[SpineEventRecord]:
        """按 category 前缀过滤；None = 不过滤。

        前缀匹配走 ``record.category.startswith(prefix)``；category 是 spine
        category 字符串（如 ``spine.cognition.brain.perceive.start``）。
        """
        for record in self.events():
            if category_prefix is None:
                yield record
                continue
            if record.category.startswith(category_prefix):
                yield record

    def read_dicts(self) -> Iterator[dict[str, Any]]:
        """逐行原样产出原始 dict —— 供旧 reader / deriver 继续消费。

        与 :meth:`events` 的差别:不做 typed 反序列化,不构造
        :class:`SpineEventRecord`;每行 ``json.loads`` 后直接 yield dict。

        使用场景:
        - CLI / deriver 仍在消费旧 ``EventRecord`` 字段（``outcome`` /
          ``when`` / ``sequence`` / ``span_id`` 等）;这些字段不在
          :class:`SpineEventRecord` 10 键 SSOT（含 ``trace_id``）内,要按 raw
          dict 透传。
        - PR-4 reader 唯一入口收口:即便读旧格式,走 SpineReader,不直 open。

        损坏行（json.JSONDecodeError）:log + skip,不 raise。
        """
        if not self._path.exists():
            log.warning(
                "SpineReader.read_dicts: file missing",
                extra={"run_id": self._run_id, "path": str(self._path)},
            )
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for line_no, raw in enumerate(fh, start=1):
                stripped = raw.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    log.warning(
                        "SpineReader.read_dicts: skip corrupted line",
                        extra={
                            "run_id": self._run_id,
                            "path": str(self._path),
                            "line_no": line_no,
                            "error": str(exc),
                        },
                    )
                    continue
                if not isinstance(data, dict):
                    log.warning(
                        "SpineReader.read_dicts: skip non-dict line",
                        extra={
                            "run_id": self._run_id,
                            "path": str(self._path),
                            "line_no": line_no,
                        },
                    )
                    continue
                yield data


__all__ = ["SpineFileMissingError", "SpineReader"]
