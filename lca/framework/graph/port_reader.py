"""PortReader — typed reader over :class:`PortRegistry`.

Resolves a :class:`PortRef` against the registry's port store, optionally
navigating into a named field on the payload. The kernel uses this in D4
to replace the legacy ``_ResultView`` interpreter indirection.

Error contract:

- Port absent from registry → :class:`UnsetPortError`.
- ``ref.field`` names a field not on the payload_type → :class:`UnknownFieldError`.
- No silent ``None`` — callers must handle the error or know the port is set.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lca.contracts.protocols.graph.errors import UnknownFieldError
from lca.contracts.protocols.graph.predicate import PortRef
from lca.framework.graph.port_registry import PortRegistry


class PortReader:
    """Reads port values from a :class:`PortRegistry` with typed field access.

    Constructed per-edge or per-predicate evaluation; holds a reference
    to the registry (not a copy) so it always sees the latest writes.
    """

    def __init__(self, registry: PortRegistry) -> None:
        self._registry = registry

    @property
    def registry(self) -> PortRegistry:
        """The underlying registry (read-only access for predicate evaluation)."""
        return self._registry

    def read(self, ref: PortRef) -> Any:
        """Resolve ``ref`` against the registry.

        - ``ref.field is None`` → return the whole port value.
        - ``ref.field is not None`` → navigate into the field.

        Raises :class:`UnsetPortError` if the port is not in the registry.
        Raises :class:`UnknownFieldError` if the field doesn't exist on
        the port's payload (dict key or payload_type attribute).
        """
        value = self._registry.read(ref.name)

        if ref.field is None:
            return value

        return self._resolve_field(ref.name, ref.field, value)

    def port_has_value(self, name: str) -> bool:
        """Check whether the port is set in the registry (without raising)."""
        return name in self._registry.snapshot()

    def _resolve_field(self, port_name: str, field_name: str, value: Any) -> Any:
        """Navigate into ``field_name`` on ``value``."""
        payload_type = self._registry.port_type(port_name)

        # Typed payload: validate field existence against the declared type.
        if payload_type is not None and issubclass(payload_type, BaseModel):
            if field_name not in payload_type.model_fields:
                raise UnknownFieldError(
                    f"port {port_name!r} payload_type {payload_type.__name__} "
                    f"has no field {field_name!r}",
                    port_name=port_name,
                )
            return getattr(value, field_name)

        # Dict payload: key lookup.
        if isinstance(value, dict):
            if field_name not in value:
                raise UnknownFieldError(
                    f"port {port_name!r} dict payload has no key {field_name!r}",
                    port_name=port_name,
                )
            return value[field_name]

        # Untyped non-dict payload: cannot resolve field.
        raise UnknownFieldError(
            f"port {port_name!r} value {type(value).__name__} does not support "
            f"field access for {field_name!r}",
            port_name=port_name,
        )


__all__ = ["PortReader"]
