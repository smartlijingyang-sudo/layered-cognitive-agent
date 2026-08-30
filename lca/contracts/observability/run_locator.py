"""RunLocator contract —— ADR-0065 §七 / PR-5。

``RunLocator`` 把 ``run_id → run_dir`` 的解析封装成 capability;fs / s3 /
multi-host layout 都通过实现该契约提供。目录命名:
- 不可猜测的 ``<run_id>`` 即目录名(不可由本地时间戳 / 部分 hash / 人类命名承担身份)
- 跨 OS 差异(Linux/macOS/Windows)封装在实现内,调用方只见 capability

默认实现:``FilesystemRunLocator``(``lca/infrastructure/observability/run_locator_fs.py``)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class RunLocator(Protocol):
    """把 run_id 解析到物理路径的契约。"""

    def run_dir(self, run_id: str) -> Path:
        """返回 run 的物理目录;若目录不存在也返回路径(写时再创建)。"""

    def journal_path(self, run_id: str) -> Path:
        """返回该 run 的 journal.jsonl 路径。"""

    def evidence_dir(self, run_id: str) -> Path:
        """返回该 run 的 evidence 子目录路径。"""

    def materialization_dir(
        self, run_id: str, *, generator_id: str, generator_version: str
    ) -> Path:
        """返回 materializations/<generator-id>/<generator-version>/ 路径。"""

    def manifest_path(self, run_id: str) -> Path:
        """返回 manifest.json 路径。"""

    def latest_pointer_path(self) -> Path:
        """返回 traces/latest.json 路径(原子指针,非事实来源)。"""

    def update_latest_pointer(self, run_id: str) -> None:
        """原子更新 latest.json(临时文件 + os.replace)。"""


__all__ = ["RunLocator"]
