"""Journal schema version constants + direction-aware check (ADR-0169 §D3 L15)。

Reader 边界使用以下常量判断格式兼容性:

- ``SCHEMA_VERSION``:当前 reader / writer 的目标 schema 版本。
- ``MIN_SUPPORTED_VERSION``:reader 仍可解析的最旧版本;低于它应报
  ``VersionTooOld`` 并提示迁移或回退。
- ``MAX_SUPPORTED_VERSION``:reader 仍可解析的最新版本;高于它应报
  ``VersionTooNew`` 并提示升级 reader 或拒绝新写入。

范围 [MIN, MAX] 内的版本视为可读;两端开区间 = 单点兼容。
"""

from __future__ import annotations

from lca.contracts.observability.journal_format_errors import (
    VersionTooNew,
    VersionTooOld,
)

SCHEMA_VERSION: int = 2

MIN_SUPPORTED_VERSION: int = 1

MAX_SUPPORTED_VERSION: int = 3


def check_schema_version(version: int) -> None:
    """对单个 ``version`` 做方向感知校验。

    Args:
        version: 待校验的 schema 版本号(读到的 envelope / record 携带)。

    Raises:
        VersionTooOld: ``version < MIN_SUPPORTED_VERSION``
        VersionTooNew: ``version > MAX_SUPPORTED_VERSION``
    """
    if version < MIN_SUPPORTED_VERSION:
        raise VersionTooOld(version, MIN_SUPPORTED_VERSION)
    if version > MAX_SUPPORTED_VERSION:
        raise VersionTooNew(version, MAX_SUPPORTED_VERSION)


__all__ = [
    "MAX_SUPPORTED_VERSION",
    "MIN_SUPPORTED_VERSION",
    "SCHEMA_VERSION",
    "check_schema_version",
]
