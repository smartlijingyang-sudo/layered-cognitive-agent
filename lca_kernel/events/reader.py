"""SpineReader —— 事实链唯一读取入口 —— ADR-0183 §3.8 + I-FW-SSOT-1。

派生系统（ProjectionDeriver / StepTreeDeriver / ExporterHook）全部从 reader 派生。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

from lca_kernel.events.spine_runtime import SpineEventRecord

log = logging.getLogger(__name__)


class SpineReader:
    """事实链唯一读取入口（I-FW-SSOT-1）。

    所有派生系统（ProjectionDeriver / StepTreeDeriver / ExporterHook）必须从
    reader 派生；禁止直读 ``<run_id>.spine.jsonl`` 文件。
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


__all__ = ["SpineReader"]
