"""``SpineRegistry`` — build-time enforcement for EXECUTION_POINTS coverage.

ADR-0165.1 §决定 1 enforces five-layer build-time checks. This module owns
the first two:

- Layer-1: every entry in :data:`~lca.infrastructure.observability.spine.manifest.EXECUTION_POINTS`
  has a registered :class:`SpineHandler` (one handler per EP).
- Layer-2: every registered handler binds both a ``wrap_fn`` and a
  ``target_module`` — half-bound specs are forbidden because they would
  silently no-op at runtime.

Why two layers and not one
--------------------------

Splitting the check makes the failure mode diagnostic. A Layer-1 violation
("missing handler for EP X") means the reflector for that EP has not been
wired into the profile; a Layer-2 violation ("handler for EP X is missing
wrap_fn or target_module") means the reflector exists but its manifest
is incomplete. The diagnostic surface is per-EP, not just "registry bad".

Lifecycle
---------

The 18 reflectors from PR-3.1–3.4 (and the upcoming PR-7 plugins)
register their wrap_fns here at plugin setup time. Kernel boot calls
:func:`lca.harness.profile.compile_spine_registry.compile_spine_registry`
which walks the loaded profile, scans the ``spine`` plugin tree for
``@plugin`` registrations, and calls :meth:`SpineRegistry.register` for
each one. ``compile_spine_registry`` returns the assembled registry; the
build-time pytest suite calls :meth:`SpineRegistry.validate` against
:data:`EXECUTION_POINTS` and fails loudly on gaps.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class SpineRegistryError(Exception):
    """Base class for SpineRegistry build-time errors."""


class IncompleteRegistry(SpineRegistryError):
    """Layer-1 violation: registry keys are missing from EXECUTION_POINTS.

    Raised by :meth:`SpineRegistry.validate` when one or more execution
    points from the validated set have no registered handler.
    """

    def __init__(self, missing: tuple[str, ...]) -> None:
        self.missing = missing
        joined = ", ".join(sorted(missing))
        super().__init__(
            f"IncompleteRegistry: {len(missing)} execution point(s) "
            f"have no registered handler: {joined}"
        )


class MissingWrapFn(SpineRegistryError):
    """Layer-2 violation: a registration is missing wrap_fn or target_module.

    Raised by :meth:`SpineRegistry.register` immediately so a profile
    author learns the manifest is half-bound at plugin load time, not
    later when the silent no-op becomes a debugging hunt.
    """

    def __init__(self, execution_point: str, missing_field: str) -> None:
        self.execution_point = execution_point
        self.missing_field = missing_field
        super().__init__(
            f"MissingWrapFn: handler for {execution_point!r} is missing {missing_field!r}"
        )


@dataclass(frozen=True, slots=True)
class SpineHandler:
    """One entry in the registry: an execution point bound to its wrap_fn.

    Attributes
    ----------
    execution_point:
        The execution point this handler instruments; must be a member
        of :data:`EXECUTION_POINTS`.
    wrap_fn:
        The function installed on the host to emit the EP event (either
        via ``ctx.effect`` for ``ctx_effect`` kind, or
        ``ctx.intercept(target_module, …, wrap_fn)`` for ``ctx_intercept``
        kind).
    target_module:
        The host module the wrap_fn binds to. Empty string is forbidden
        (Layer-2).
    """

    execution_point: str
    wrap_fn: Callable[..., Any]
    target_module: str


class SpineRegistry:
    """Build-time spine handler registry.

    Storage is ordered (a dict) so :meth:`keys` returns a stable, ordered
    view of the registration sequence — useful for diagnostics and for
    the runtime boot hook that logs coverage gaps.

    The registry does NOT enforce uniqueness of ``wrap_fn`` per EP. A
    single EP must have at most one handler (the close-set intent of
    EXECUTION_POINTS), but the registry itself trusts the caller to
    register each EP once; duplicate registrations are a Layer-2-style
    symptom of a malformed manifest and the pytest suite catches it
    upstream.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, SpineHandler] = {}

    def register(
        self,
        *,
        execution_point: str,
        wrap_fn: Callable[..., Any] | None,
        target_module: str,
    ) -> SpineHandler:
        """Register a handler for ``execution_point``.

        Raises
        ------
        MissingWrapFn
            If ``wrap_fn`` is ``None`` (Layer-2 wrap-fn unbound).
        MissingWrapFn
            If ``target_module`` is empty (Layer-2 target unbound).
        """
        if wrap_fn is None:
            raise MissingWrapFn(execution_point, "wrap_fn")
        if not target_module:
            raise MissingWrapFn(execution_point, "target_module")
        handler = SpineHandler(
            execution_point=execution_point,
            wrap_fn=wrap_fn,
            target_module=target_module,
        )
        self._handlers[execution_point] = handler
        return handler

    def keys(self) -> tuple[str, ...]:
        """Return the registered execution points in insertion order."""
        return tuple(self._handlers)

    def get(self, execution_point: str) -> Callable[..., Any] | None:
        """Return the wrap_fn for ``execution_point`` or ``None`` if absent."""
        handler = self._handlers.get(execution_point)
        return None if handler is None else handler.wrap_fn

    def get_handler(self, execution_point: str) -> SpineHandler | None:
        """Return the full :class:`SpineHandler` for ``execution_point``."""
        return self._handlers.get(execution_point)

    def __len__(self) -> int:
        return len(self._handlers)

    def __contains__(self, execution_point: object) -> bool:
        return execution_point in self._handlers

    def validate(self, execution_points: tuple[str, ...]) -> None:
        """Assert registry keys ⊇ ``execution_points`` (Layer-1).

        Raises
        ------
        IncompleteRegistry
            If one or more ``execution_points`` are missing from
            :meth:`keys`.
        """
        registered = set(self._handlers)
        missing = tuple(point for point in execution_points if point not in registered)
        if missing:
            raise IncompleteRegistry(missing)


__all__ = [
    "IncompleteRegistry",
    "MissingWrapFn",
    "SpineHandler",
    "SpineRegistry",
    "SpineRegistryError",
]
