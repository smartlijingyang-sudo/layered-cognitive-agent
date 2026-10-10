"""EventIdentity provider seam —— 读侧 (ADR-0096 MVA-2 + ADR-0097)。

写侧：``lca.plugins.observability.event.identity_seam`` 在 boot 时把
``StableUlidIdentity``（或替代实现）经 :func:`install_identity_provider`
装进这里；读侧：``RunStore`` 等 infrastructure 代码经
:func:`resolve_identity_provider` 取实现，不再直引 ``lca.plugins``
（包契约 pin）。

未装配时回退 ``StableUlidIdentity`` —— 与 seam 引入前的默认行为一致，
零行为变更。
"""

from __future__ import annotations

from lca.contracts.observability.event.identity import EventIdentityProvider
from lca.contracts.observability.event.stable_ulid_identity import StableUlidIdentity

_active_provider: EventIdentityProvider | None = None


def install_identity_provider(
    provider: EventIdentityProvider | None,
) -> EventIdentityProvider | None:
    """安装进程级 identity provider；返回旧值以便调用方恢复（测试常用）。"""
    global _active_provider
    previous = _active_provider
    _active_provider = provider
    return previous


def resolve_identity_provider() -> EventIdentityProvider:
    """返回已安装的 provider；未装配时回退默认 ``StableUlidIdentity``。"""
    if _active_provider is not None:
        return _active_provider
    return StableUlidIdentity()


__all__ = ["install_identity_provider", "resolve_identity_provider"]
