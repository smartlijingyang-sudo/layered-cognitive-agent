"""观测面 SSOT 注册表(ADR-0169 L10 / PR-27 / PR-4)。

本模块是文件名 / 路径派生的单一权威。任何 reader / writer 必须通过
下列函数得到 per-run artifact 的物理路径,**禁止** 再有
``run_dir / "<run_id>.spine.jsonl"`` 之类的字符串拼接。

本模块同时 re-export append 型持久化的 :class:`FsyncProtocol` 闭集
(定义在 :mod:`lca.contracts.observability.fsync`,该模块零依赖):
"何时 fsync" 是契约,落盘实现(sinks / persistence observer)必须
按枚举显式声明自己的节奏,禁止隐式行为或平行枚举
(见 docs/notes/proposed/seam/2026-09-03-2-seam-fsync-semantics.md)。

历史回归根因:
- spine 文件名字符串被多处 reader / writer 硬编码;
- 一旦 FileSink 的默认文件名在 PR-27 改成 ``$run_id.spine.jsonl``,
  所有未同步的 reader 立刻读到全零、H-xref 永远 ok、bug 沉默通过;
- exception 落盘文件名 ``<run_id>.exceptions.jsonl`` 同理被多处字符串拼。

收口:
- :func:`find_spine_file` 取代所有 spine 字面 reader,只走
  ``<run_dir>/<run_id>.spine.jsonl``(PR-4 已无 legacy 兜底);缺失抛
  :class:`ObservationSSOTError`。
- :func:`find_exceptions_file` 取代所有 ``<run_id>.exceptions.jsonl``
  字面 reader;同样走 spine 命名 + 不存在抛错。
- :func:`find_kernel_log` 取代 ``kernel.log`` 字面 reader。

Wire contract 的语义边界:
- 只看 per-run directory (``<run_dir>``);``boot-spine.jsonl`` /
  ``oii-debug-boot-spine.jsonl`` 等 boot 事件命名空间不进本模块(boot
  事件走独立命名空间,见 ADR-0165.1 / ADR-0167 D11 / PR-4)。
- 所有函数在 ``<run_dir>`` 不存在或文件名不在预期之一时抛错,
  避免 silent zero。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.observability.fsync import FsyncProtocol as FsyncProtocol
from lca.infrastructure.observability.spine.sinks.naming import (
    exceptions_filename_for_run,
    kernel_log_filename,
    spine_filename_for_run,
)


class ObservationSSOTError(FileNotFoundError):
    """观测面 SSOT 解析失败(单文件缺失,不是 silent zero)。"""


def find_spine_file(run_dir: Path, run_id: str) -> Path:
    """Return the canonical spine ledger path for ``run_id`` in ``run_dir``.

    PR-4 收口:只走 ``<run_dir>/<run_id>.spine.jsonl``(spine 命名 SSOT);
    缺失抛 :class:`ObservationSSOTError`。

    Contract:
    - 只看 per-run ``<run_dir>``;boot / benchmark 事件流不进本函数。
    - 调用方不应再做 ``.exists()`` 二次校验;SSOT 抛错即失败。
    """
    if not run_dir.exists():
        raise ObservationSSOTError(f"run_dir does not exist: {run_dir} (run_id={run_id})")
    spine_path = run_dir / spine_filename_for_run(run_id)
    if not spine_path.exists():
        raise ObservationSSOTError(
            f"spine ledger not found in {run_dir} (looked for {spine_path.name})"
        )
    return spine_path


def find_exceptions_file(run_dir: Path, run_id: str) -> Path:
    """Return the canonical exceptions index path for ``run_id``.

    期望 ``<run_dir>/<run_id>.exceptions.jsonl``。缺失抛
    :class:`ObservationSSOTError`(``exception.caught`` 事件若未发则本
    文件自然不存在,reader 必须显式 try/except 区分"文件不存在"与
    "读盘失败")。
    """
    if not run_dir.exists():
        raise ObservationSSOTError(f"run_dir does not exist: {run_dir} (run_id={run_id})")
    return run_dir / exceptions_filename_for_run(run_id)


def find_kernel_log(run_dir: Path, run_id: str) -> Path:
    """Return the canonical kernel log path for ``run_id``.

    返回 ``<run_dir>/kernel.log``;``run_dir`` 不存在抛
    :class:`ObservationSSOTError`。与 spine / exceptions 不同,文件本身
    缺失是常态(唯一写者是失败兜底 ``record_run_failure``,多数 run 无
    此文件),本函数**不**对文件缺失抛错,调用方需自行 ``.exists()``。
    """
    if not run_dir.exists():
        raise ObservationSSOTError(f"run_dir does not exist: {run_dir} (run_id={run_id})")
    return run_dir / kernel_log_filename(run_id)


__all__ = [
    "FsyncProtocol",
    "ObservationSSOTError",
    "find_exceptions_file",
    "find_kernel_log",
    "find_spine_file",
]
