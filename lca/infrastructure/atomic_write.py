"""原子覆盖写原语 —— 派生产物落盘的唯一机制。

覆盖写产物(``journal.json`` / ``journal.narrative.md`` / ``manifest.json``)
共用本入口:同目录临时文件 + ``os.replace`` 原子替换,读方任何时刻
看到的要么是旧内容、要么是完整新内容,不会读到半截文件。

与追加流的分工:``<run_id>.spine.jsonl`` / ``<run_id>.session.jsonl`` /
``<run_id>.exceptions.jsonl`` 是运行中逐条追加的真值流,各自有
append + flush/fsync 语义(``FileSink`` / ``JsonlSessionPersistence``),
不走本模块。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

__all__ = ["atomic_write_text"]


def atomic_write_text(path: str | Path, text: str, *, encoding: str = "utf-8") -> Path:
    """把 ``text`` 原子覆盖写到 ``path``。

    precondition: ``path`` 的父目录已存在或可创建。
    失败语义: 临时文件写入或替换失败时清理临时文件并原样上抛;
    目标文件保持替换前的内容。
    时序: 同目录建临时文件 → 写全量 → ``os.replace`` 原子替换。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding=encoding,
        dir=str(target.parent),
        prefix=target.name + ".",
        suffix=".tmp",
        delete=False,
    ) as fh:
        fh.write(text)
        tmp_path = Path(fh.name)
    try:
        tmp_path.replace(target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return target
