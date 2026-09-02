"""Journal format refusal errors —— ADR-0169 §D3 L15。

方向感知的格式拒绝:reader 在解析 envelope / journal 记录时,根据
``SCHEMA_VERSION`` 与 ``event_type`` 的相对位置给出明确错误子类,便于上层
做错误码分发 / 升级路径决策 / 灰度治理。

错误分类:
- ``VersionTooOld``  : 记录 schema 早于 reader 最小支持版本 —— 通常表示
  需要迁移或回退到旧 reader。
- ``VersionTooNew``  : 记录 schema 晚于 reader 最大支持版本 —— 通常表示
  需要升级 reader 或主动拒绝新写入。
- ``UnknownEventType``: event_type 不在 reader 已知词表内,且 envelope 未
  携带 ``ignorable=true`` 标记 —— 表示不可静默跳过,需要登记或升级。
"""

from __future__ import annotations


class JournalFormatError(Exception):
    """L15: journal 格式拒绝的公共基类。"""


class VersionTooOld(JournalFormatError):  # noqa: N818 — name mandated by ADR-0169 §D3 L15
    """记录 ``SCHEMA_VERSION`` 小于 reader 的最小支持版本。"""

    def __init__(self, schema_version: int, min_supported: int) -> None:
        self.schema_version = schema_version
        self.min_supported = min_supported
        super().__init__(f"journal schema_version={schema_version} < min_supported={min_supported}")


class VersionTooNew(JournalFormatError):  # noqa: N818 — name mandated by ADR-0169 §D3 L15
    """记录 ``SCHEMA_VERSION`` 大于 reader 的最大支持版本。"""

    def __init__(self, schema_version: int, max_supported: int) -> None:
        self.schema_version = schema_version
        self.max_supported = max_supported
        super().__init__(f"journal schema_version={schema_version} > max_supported={max_supported}")


class UnknownEventType(JournalFormatError):  # noqa: N818 — name mandated by ADR-0169 §D3 L15
    """未知的 ``event_type`` 且非 ``ignorable``。"""

    def __init__(self, event_type: str) -> None:
        self.event_type = event_type
        super().__init__(f"unknown journal event_type={event_type!r} and not ignorable")


__all__ = [
    "JournalFormatError",
    "UnknownEventType",
    "VersionTooNew",
    "VersionTooOld",
]
