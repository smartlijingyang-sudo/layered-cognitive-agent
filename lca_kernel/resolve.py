"""Profile 解析领域校验(K1b)。

ADR-0115 决定 1 K1b:PR-2 阶段薄 re-export :mod:`lca.harness.profile.resolve`,
公共函数名 + 签名 + 行为不变。完整迁移留待后续阶段。
"""

from __future__ import annotations

from lca.harness.profile.resolve import (
    ProfileResolveError,
    ResolvedPlugin,
    ResolvedProfile,
    dump_resolved,
    resolve_entries,
    resolve_profile,
)

__all__ = [
    "ProfileResolveError",
    "ResolvedPlugin",
    "ResolvedProfile",
    "dump_resolved",
    "resolve_entries",
    "resolve_profile",
]
