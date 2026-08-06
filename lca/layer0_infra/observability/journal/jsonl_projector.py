"""JsonlJournalProjector —— journal 落盘投影（ADR-0037 record-as-data）。

每个盖章事件一行 JSON（schema 版本化），jq 可查、replay 可重建。
替代旧 span 级 JsonlExporter：落盘的是叙事真相（journal），不是 span 形状。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from lca.contracts.journal import StampedEvent
from lca.contracts.protocols import JournalProjector
from lca.layer0_infra.observability.journal.journal_io import stamped_to_record


class JsonlJournalProjector(JournalProjector):
    """journal 事件逐行追加写入 jsonl 文件。"""

    def __init__(self, output_path: str | Path = "traces/lca_journal.jsonl") -> None:
        self._path = Path(output_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: TextIO = self._path.open("a", encoding="utf-8")

    def on_event(self, stamped: StampedEvent) -> None:
        self._fh.write(json.dumps(stamped_to_record(stamped), ensure_ascii=False) + "\n")
        self._fh.flush()  # trace 文件逐行持久：进程崩溃不丢已记录事件

    def flush(self) -> None:
        self._fh.flush()

    def close(self) -> None:
        self.flush()
        self._fh.close()
