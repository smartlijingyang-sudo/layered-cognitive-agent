"""port_values → :class:`PhaseOutput` projection (pure function).

Used by :class:`lca.framework.subgraph.plugins.node_graph_driver.NodeGraphDriver`
at terminal iteration to publish the graph's terminal contribution into
the run-scoped :class:`PhaseOutputChannel`.

Why a pure function (no Cordis / no plugin):
- The driver already owns the ``port_values`` dict; a second seam just
  to call this function would only complicate testing.
- ``project_port_values_to_phase_output`` must be deterministic and
  trivially testable; it has no I/O, no scope access, no clock.

Per ADR-0219 §10.11.5: the field set is owned by
:data:`lca.cognition.close_out.CLOSE_OUT_FIELDS`. This module imports
the tuple and walks it; no field-name literal lives here.

Unknown keys are silently ignored — only the canonical fields are
forwarded. Type mismatches (e.g. ``str`` for ``decision``) raise
``PhaseOutput``'s frozen Pydantic validator; the function does not
silently coerce.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from lca.cognition.close_out import CLOSE_OUT_FIELDS
from lca.framework.subgraph.plugins.channel import PhaseOutput


def project_port_values_to_phase_output(
    port_values: Mapping[str, Any],
) -> PhaseOutput:
    """Project the driver-collected ``port_values`` dict into a ``PhaseOutput``.

    Each canonical key, when present, contributes to its typed field.
    Missing keys yield ``None``. The returned ``PhaseOutput`` is
    immutable (Pydantic ``frozen=True``); downstream consumers must
    not mutate it.
    """
    kwargs: dict[str, Any] = {
        field_name: port_values.get(field_name) for field_name in CLOSE_OUT_FIELDS
    }
    return PhaseOutput(**kwargs)


__all__ = ["project_port_values_to_phase_output"]
