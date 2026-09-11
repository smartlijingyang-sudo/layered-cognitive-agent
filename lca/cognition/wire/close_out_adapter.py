"""CloseOutAdapter — the seam the framework graph kernel calls.

This is the single ACL class that framework code can import without
breaking the layer rule. It hides:

- which :data:`CLOSE_OUT_REGISTRY` fields are wired up;
- how priorities resolve when multiple inner outputs collide;
- the typed payload classes each field carries.

The framework sees only port names (:data:`lca.contracts.protocols.graph.ports.PortName`)
and gets back a plain ``dict[str, Any]``. The cognition layer owns the
mapping from port name to business DTO.

Why this class instead of free functions:

- Future graph kernel (planned PR-4) will inject this adapter at boot,
  allowing test fixtures to swap in a custom projection policy
  without rewriting the kernel.
- The registry lookup happens once per adapter construction, not per
  visit. The hot path (:meth:`project`) is just a dict comprehension.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from lca.cognition.wire.close_out_registry import (
    CLOSE_OUT_REGISTRY,
    CloseOutField,
    close_out_projection,
)


@dataclass(frozen=True, slots=True)
class CloseOutAdapter:
    """The framework-facing ACL for close-out projection.

    Defaults to the production :data:`CLOSE_OUT_REGISTRY`. Tests and
    alternative projections may pass a custom ``fields`` tuple to
    narrow or reorder the projection surface.
    """

    fields: tuple[CloseOutField, ...] = field(default_factory=lambda: CLOSE_OUT_REGISTRY)

    def project(self, inner_outputs: Mapping[Any, Any]) -> dict[str, Any]:
        """Project inner outputs through this adapter's field set.

        Returns a plain dict keyed by field name. Empty when no
        inner output produced a recognized field.
        """
        if self.fields is CLOSE_OUT_REGISTRY:
            return close_out_projection(inner_outputs)
        # Custom field set: build a one-off registry-shaped mapping.
        custom: dict[str, Any] = {}
        sorted_fields = sorted(self.fields, key=lambda f: -f.priority)
        for fld in sorted_fields:
            for output in inner_outputs.values():
                if not hasattr(output, fld.name):
                    continue
                value = getattr(output, fld.name, None)
                if value is not None and fld.name not in custom:
                    custom[fld.name] = value
                    break
        return custom

    def field_names(self) -> tuple[str, ...]:
        """Return the field names this adapter recognizes, in priority order."""
        return tuple(f.name for f in sorted(self.fields, key=lambda f: -f.priority))

    def payload_types(self) -> dict[str, type]:
        """Return the field name → payload type mapping.

        Useful for runtime type-check helpers. Keys are field names;
        values are the business DTO classes.
        """
        return {f.name: f.payload_type for f in self.fields}


__all__ = ["CloseOutAdapter"]