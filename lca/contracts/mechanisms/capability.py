"""Capability context — Definition 拥有的活服务键（DSH ctx 的 Python 形态）。

cordis migration: SeamKey → CapabilityKey rename. CapabilityHub / mount /
require / get are replaced by cordis.Context.provide / inject; the
CapabilityContext Protocol is kept for migration-period back-compat.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, runtime_checkable


class CapabilityKey(str, Enum):
    """全部能力接缝键。仅可替换后端进此表；编排（Brain/Loop/Team）不是 seam。"""

    LLM = "llm"
    SANDBOX = "sandbox"
    MEMORY = "memory"
    STATE_STORE = "state_store"
    SEARCH = "search"
    TOOLS = "tools"
    TRANSPORT = "transport"
    SKILLS = "skills"
    FILE_STORE = "file_store"
    OBSERVABILITY = "observability"


REQUIRED_CAPABILITY_KEYS: tuple[CapabilityKey, ...] = tuple(CapabilityKey)

# ── Deprecated alias (back-compat for migration period) ──


# Re-export SeamKey as deprecated alias pointing to CapabilityKey
def __getattr__(name: str) -> object:
    if name == "SeamKey":
        import warnings
        warnings.warn(
            "SeamKey is deprecated; use CapabilityKey instead",
            DeprecationWarning,
            stacklevel=3,
        )
        return CapabilityKey
    if name == "REQUIRED_SEAM_KEYS":
        import warnings
        warnings.warn(
            "REQUIRED_SEAM_KEYS is deprecated; use REQUIRED_CAPABILITY_KEYS instead",
            DeprecationWarning,
            stacklevel=3,
        )
        return REQUIRED_CAPABILITY_KEYS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class MissingCapabilityError(KeyError):
    """ctx 上尚未 mount 该 Definition。"""


def require_capability(ctx: object, key: str) -> Any:
    """Read ``key`` from a booted cordis Context. Missing → MissingCapabilityError.

    Execute / compose call this instead of module-level factories. A None
    ctx, a ctx without ``inject``, a KeyError, or an explicit None binding
    are all the same miss — there is no silent fallback.
    """
    if ctx is None:
        raise MissingCapabilityError(key)
    inject = getattr(ctx, "inject", None)
    if not callable(inject):
        raise MissingCapabilityError(key)
    try:
        value = inject(key)
    except KeyError as exc:
        raise MissingCapabilityError(key) from exc
    if value is None:
        raise MissingCapabilityError(key)
    return value


def provider_current(svc: object) -> object | None:
    """Active provider on a Definition service, or None when the table is empty."""
    providers = getattr(svc, "providers", None)
    if providers is None:
        current = getattr(svc, "current", None)
        if callable(current):
            try:
                return current()
            except Exception:
                return None
        return svc
    if not getattr(providers, "active", None):
        return None
    return providers.current()


@runtime_checkable
class CapabilityContext(Protocol):
    """活接缝上下文：键上只有 Definition 服务。

    Back-compat shim — replaced by cordis.Context.provide / inject.
    """

    def mount(self, key: str, service: Any) -> None: ...

    def require(self, key: str) -> Any: ...

    def get(self, key: str) -> Any | None: ...

    def keys(self) -> list[str]: ...
