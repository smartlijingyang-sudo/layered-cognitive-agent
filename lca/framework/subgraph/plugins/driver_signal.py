"""port_values → :class:`PhaseOutput` projection (pure function).

Used by :class:`lca.framework.subgraph.plugins.node_graph_driver.NodeGraphDriver`
at terminal iteration to publish the graph's terminal contribution into
the run-scoped :class:`PhaseOutputChannel`.

Why a pure function (no Cordis / no plugin):
- The driver already owns the ``port_values`` dict; a second seam just
  to call this function would only complicate testing.
- ``project_port_values_to_phase_output`` must be deterministic and
  trivially testable; it has no I/O, no scope access, no clock.

Mapping (per plan §13.5):

- ``port_values["decision"]`` → ``output.decision``
- ``port_values["observation"]`` → ``output.observation``
- ``port_values["reflection"]`` → ``output.reflection``
- ``port_values["response"]`` → ``output.response``

Unknown keys are silently ignored — only the four canonical fields
are forwarded. Type mismatches (e.g. ``str`` for ``decision``) raise
``PhaseOutput``'s frozen Pydantic validator; the function does not
silently coerce.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
    return PhaseOutput(
        decision=port_values.get("decision"),
        observation=port_values.get("observation"),
        reflection=port_values.get("reflection"),
        response=port_values.get("response"),
    )


__all__ = ["project_port_values_to_phase_output"]
