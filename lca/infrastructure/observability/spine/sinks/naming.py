"""ADR-0169 L10:spine 文件名约定常量 + 派生函数。

PR-2 / S2 引入 ``SPINE_FILE_SUFFIX = ".spine.jsonl"`` 常量,允许 sink 选择启用
新文件名(``<run_id>.spine.jsonl``);旧默认值 ``events.jsonl`` 保留以不破坏
既有 tests/生产路径(只挂"路径单写"语义,L10)。

未来 PR-25 装配时,RoutingFileSink / FileSink 默认启用 ``spine_filename=True``;
本 PR 不改默认(避免大爆炸),仅提供约定 + 派生函数。
"""

from __future__ import annotations

# COMPAT(delete-when: PR-25 装配启用 spine_filename=True 默认值, tracking: ADR-0169-task-PR-2)
SPINE_FILE_SUFFIX = ".spine.jsonl"

# 旧文件名(向后兼容;RouterFileSink 默认使用 ``<run_dir>/events.jsonl``)
LEGACY_FILE_NAME = "events.jsonl"


def spine_filename_for_run(run_id: str) -> str:
    """派生 per-run spine 文件名(ADR-0169 L10)。

    >>> spine_filename_for_run("run_abc")
    'run_abc.spine.jsonl'
    """
    return f"{run_id}{SPINE_FILE_SUFFIX}"


__all__ = [
    "LEGACY_FILE_NAME",
    "SPINE_FILE_SUFFIX",
    "spine_filename_for_run",
]
