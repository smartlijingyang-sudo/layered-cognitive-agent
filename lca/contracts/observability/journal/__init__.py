"""Observability journal contracts — typed exceptions + DTOs。

子模块:
- :mod:`.errors` —— :class:`JournalWriteError`(ADR-0212):观测面写盘失败 fail-loud。
- :mod:`.format_errors` —— :class:`JournalFormatError`:读端 schema 拒绝。
- :mod:`.formatter` / :mod:`.ledger` / :mod:`.run_journal` / :mod:`.store` —— DTO 与 schema。
"""

from lca.contracts.observability.journal.errors import JournalWriteError
from lca.contracts.observability.journal.format_errors import (
    JournalFormatError,
    UnknownEventType,
    VersionTooNew,
    VersionTooOld,
)

__all__ = [
    "JournalFormatError",
    "JournalWriteError",
    "UnknownEventType",
    "VersionTooNew",
    "VersionTooOld",
]
