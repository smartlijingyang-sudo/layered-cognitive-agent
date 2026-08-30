"""Default filename blacklist + whitelist for LCA.

Override per package in pyproject.toml [tool.lca.package_contracts.<pkg>]
via `filename_whitelist` and `filename_blacklist_extra` fields.

Public API:
- DEFAULT_BLACKLIST: list of fnmatch patterns
- DEFAULT_WHITELIST: list of fnmatch patterns (overrides blacklist)
- is_blacklisted(rel_path, extra_blacklist=None) -> bool
- is_whitelisted(rel_path, package_whitelist=None) -> bool
"""

from __future__ import annotations

from fnmatch import fnmatch

# 默认 blacklist 模式（来自 docs/specs/naming-conventions.md）
DEFAULT_BLACKLIST: list[str] = [
    "*util*.py",
    "*helper*.py",
    "*manager*.py",
    "*impl*.py",
    "*common*.py",
    "*misc*.py",
]

# 默认 whitelist（blacklist 命中但允许；这些是包标识，不是模糊命名）
DEFAULT_WHITELIST: list[str] = [
    "lca/__init__.py",
    "lca/contracts/__init__.py",
    "lca/contracts/**/__init__.py",
    "lca/harness/__init__.py",
    "lca/harness/**/__init__.py",
    "lca/plugins/__init__.py",
    "lca/plugins/**/__init__.py",
    "lca/infrastructure/__init__.py",
    "lca/infrastructure/**/__init__.py",
    "lca/cognition/__init__.py",
    "lca/cognition/**/__init__.py",
    "lca/runtime/__init__.py",
    "lca/runtime/**/__init__.py",
    "lca/agent/__init__.py",
    "lca/agent/**/__init__.py",
    "lca/application/__init__.py",
    "lca/application/**/__init__.py",
    "gateway/__init__.py",
    "gateway/**/__init__.py",
]


def is_blacklisted(rel_path: str, extra_blacklist: list[str] | None = None) -> bool:
    """Return True if filename matches any blacklist pattern."""
    patterns = DEFAULT_BLACKLIST + (extra_blacklist or [])
    return any(fnmatch(rel_path, p) for p in patterns)


def is_whitelisted(rel_path: str, package_whitelist: list[str] | None = None) -> bool:
    """Return True if filename matches any whitelist pattern."""
    patterns = DEFAULT_WHITELIST + (package_whitelist or [])
    return any(fnmatch(rel_path, p) for p in patterns)
