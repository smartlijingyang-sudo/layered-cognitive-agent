#!/usr/bin/env python3
"""replay journal —— 从 jsonl 落盘重建运行叙事（ADR-0037 record-as-data）。

执行日志是主数据：跑完一次 run 后，无需重跑、无需连后端，直接离线重放。

Examples
--------
  # 先用 jsonl 后端落盘
  LCA_OBS_BACKENDS=console+jsonl uv run python scripts/run_scenario_file.py <yaml>

  # 离线重放（Run Card / 叙事 / 序列图）
  uv run python scripts/replay_journal.py traces/lca_journal.jsonl
  uv run python scripts/replay_journal.py traces/lca_journal.jsonl --verbosity verbose
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lca.layer0_infra.observability.journal.console_projector import (  # noqa: E402
    ConsoleJournalProjector,
)
from lca.layer0_infra.observability.journal.journal_io import (  # noqa: E402
    JournalFormatError,
    read_journal,
)
from lca.layer0_infra.observability.policy import Verbosity  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="离线重放 journal jsonl")
    parser.add_argument("path", help="journal jsonl 文件路径")
    parser.add_argument(
        "--verbosity",
        default=Verbosity.STANDARD.value,
        choices=[v.value for v in Verbosity],
        help="重放信息量档位（默认 standard；verbose 附 I/O 预览 + 序列图）",
    )
    args = parser.parse_args()

    try:
        events = read_journal(args.path)
    except JournalFormatError as err:
        print(f"journal 读取失败：{err}", file=sys.stderr)
        return 1
    if not events:
        print(f"journal 为空：{args.path}", file=sys.stderr)
        return 1

    projector = ConsoleJournalProjector(Verbosity(args.verbosity))
    for stamped in events:
        projector.on_event(stamped)
    projector.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
