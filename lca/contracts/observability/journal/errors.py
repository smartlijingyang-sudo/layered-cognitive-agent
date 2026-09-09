"""Journal write refusal errors —— ADR-0212。

观测面失败 = 事实面事件。journal.json 写盘失败必须 raise,不再 swallow;
caller 据此决定 retry / abort / 升级路径,而不是 silent failure 留下
stale 写入(典型症状:run_f78f66322f1d 的 doctor H3 重复 step_id)。

与 :mod:`.format_errors` 的 ``JournalFormatError`` 同语义层 —— 读端拒
绝 / 写端失败都是观测面的 fail-loud,登记到 contracts 层做 typed dispatch。
"""

from __future__ import annotations

from pathlib import Path


class JournalWriteError(RuntimeError):
    """journal.json 写盘失败。

    Raises:
        :class:`JournalWriteError` —— ``StepTreeFoldDeriver.derive()`` /
        :meth:`StepTreeFoldDeriver.flush()` 在 ``JournalDocumentWriter.write``
        抛 OSError / IOError / 同语义异常时透传,带 ``run_id`` 与目标路径
        便于 caller 决定 retry / abort / 升级。
    """

    def __init__(self, run_id: str, target: Path, original: BaseException) -> None:
        self.run_id = run_id
        self.target = Path(target)
        self.original = original
        super().__init__(
            f"journal.json write failed run_id={run_id} target={target}: "
            f"{type(original).__name__}: {original}"
        )


__all__ = ["JournalWriteError"]
