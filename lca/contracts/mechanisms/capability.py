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

    Resolution order (DSH-style):

    1. ``ctx.inject("<key>")`` — primary path through the plain-key
       Tier-1 binding (the Definition service instance). This matches
       the DSH ``ctx.<service>`` access shape and is the canonical
       resolution for plugins (providers, sensors, runtime, etc.).
    2. ``ctx.inject("seam:<key>").current()`` — fallback through the
       :class:`SeamRegistry` written by ``lca.seam.definitions``.
       Useful when no Tier-1 service plugin runs but the seam registry
       has been populated by other plugins (e.g. test fixtures).

    Execute / compose call this instead of module-level factories. A None
    ctx, a ctx without ``inject``, a KeyError, or an explicit None binding
    are all the same miss — there is no silent fallback.
    """
    if ctx is None:
        raise MissingCapabilityError(key)
    inject = getattr(ctx, "inject", None)
    if not callable(inject):
        raise MissingCapabilityError(key)
    # Path 1: plain-key binding — preferred (DSH ``ctx.<service>`` parity).
    try:
        value = inject(key)
    except KeyError:
        value = None
    if value is not None:
        return value
    # Path 2: seam-namespaced registry (after seam_definitions runs).
    try:
        registry = inject(f"seam:{key}")
    except KeyError as exc:
        raise MissingCapabilityError(key) from exc
    if registry is not None:
        current = getattr(registry, "current", None)
        if callable(current):
            value = current()
            if value is not None:
                return value
    raise MissingCapabilityError(key)


def provider_current(svc: object) -> object | None:
    """Active provider on a Definition service, or None when the table is empty.

    Two shapes are accepted:

    * Tier-1 Definition service with ``providers`` attribute (LCA legacy):
      returns ``providers.current()`` (the registered adapter).
    * :class:`SeamRegistry` (new seam shape): returns ``current()`` directly
      (the registered Definition service).
    """
    if svc is None:
        return None
    # SeamRegistry shape — has its own .current() returning the registered
    # provider (which is typically a Definition service).
    if hasattr(svc, "providers"):
        # Tier-1 Definition service — pull the active adapter.
        providers = svc.providers
        if not getattr(providers, "active", None):
            return None
        try:
            return providers.current()
        except Exception:
            return None
    # Direct .current() (a plain SeamRegistry or a service with no nested providers).
    current_attr = getattr(svc, "current", None)
    if callable(current_attr):
        try:
            return current_attr()
        except Exception:
            return None
    # Bare service — return as-is.
    return svc


@runtime_checkable
class CapabilityContext(Protocol):
    """活接缝上下文：键上只有 Definition 服务。

    Back-compat shim — replaced by cordis.Context.provide / inject.
    """

    def mount(self, key: str, service: Any) -> None: ...

    def require(self, key: str) -> Any: ...

    def get(self, key: str) -> Any | None: ...

    def keys(self) -> list[str]: ...
