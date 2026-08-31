"""Profile 声明的纯处理逻辑(K1c)。

ADR-0115 决定 1 K1c:PR-2 阶段薄 re-export :mod:`lca.harness.profile.declarations`,
公共函数名 + 签名 + 行为不变。
"""

from __future__ import annotations

from lca.harness.profile.declarations import (
    apply_patches,
    deep_copy_value,
    deep_merge,
    expand_entry_environment,
    expand_env_refs,
    flatten_keys,
)

__all__ = [
    "apply_patches",
    "deep_copy_value",
    "deep_merge",
    "expand_entry_environment",
    "expand_env_refs",
    "flatten_keys",
]
