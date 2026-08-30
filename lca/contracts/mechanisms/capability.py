"""Capability context — Definition 拥有的活服务键。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Protocol, cast, runtime_checkable


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
    """Read one declared capability without exposing a second plugin interface.

    Manifest plugins run through ``AuditedPluginContext`` and therefore use
    ``require`` so the interaction is checked against the plugin declaration.
    A booted Cordis carrier has no such audited method and retains ``inject``
    as its internal lookup operation.  Neither route permits a legacy
    ``seam:<key>`` fallback.
    """
    if ctx is None:
        raise MissingCapabilityError(key)
    require = getattr(ctx, "require", None)
    lookup = require if callable(require) else getattr(ctx, "inject", None)
    if not callable(lookup):
        raise MissingCapabilityError(key)
    try:
        value = lookup(key)
    except KeyError as exc:
        raise MissingCapabilityError(key) from exc
    if value is None:
        raise MissingCapabilityError(key)
    return value


def provider_current(svc: object) -> object | None:
    """Active provider on a Definition service, or None when the table is empty."""
    if svc is None:
        return None
    if hasattr(svc, "providers"):
        providers = svc.providers
        if not getattr(providers, "active", None):
            return None
        try:
            return cast("object", providers.current())
        except Exception:
            return None
    current_attr = getattr(svc, "current", None)
    if callable(current_attr):
        try:
            return cast("object", current_attr())
        except Exception:
            return None
    return svc


@runtime_checkable
class CapabilityContext(Protocol):
    """活接缝上下文：键上只有 Definition 服务。"""

    def mount(self, key: str, service: Any) -> None: ...

    def require(self, key: str) -> Any: ...

    def get(self, key: str) -> Any | None: ...

    def keys(self) -> list[str]: ...
