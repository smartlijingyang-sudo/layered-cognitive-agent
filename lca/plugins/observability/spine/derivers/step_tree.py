"""spine.deriver.step_tree — boot-safe StepTree deriver plugin.

Full ``StepTreeDeriver`` wiring needs a run-scoped ``StepGroupedBackend``
(``output_path`` + ``StepLifecycleStore``). That binding is deferred to
spine.core / terminalizer composition. This plugin provides a thin
``Deriver`` stub so the Profile DAG boots without journal backends.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.derivers.base import Deriver
from lca.infrastructure.observability.spine.event_record import EventRecord

log = logging.getLogger(__name__)


class StepTreeDeriverPlugin(Deriver):
    """Boot-safe step-tree deriver stub (full backend wiring deferred).

    ``on_event`` counts live events for observability; ``flush`` is a
    no-op until a ``StepGroupedBackend`` is injected by later composition.
    """

    def __init__(self) -> None:
        self._event_count: int = 0

    @property
    def event_count(self) -> int:
        """Number of live events observed (test / diagnostics seam)."""
        return self._event_count

    def on_event(self, event: EventRecord) -> None:
        """Accumulate live-event counts; skip orphans (ADR-0165.1 §19)."""
        try:
            if event.phase != "live":
                return
            self._event_count += 1
            log.debug(
                "step_tree_deriver_plugin saw event execution_point=%s sequence=%s",
                event.execution_point,
                event.sequence,
            )
        except Exception as exc:
            log.warning(
                "step_tree_deriver_plugin.on_event failed err=%s",
                exc,
                exc_info=True,
            )

    def flush(self) -> None:
        """Stub flush — full journal.json projection needs StepGroupedBackend."""
        log.debug(
            "step_tree_deriver_plugin.flush stub (events=%s; backend wiring deferred)",
            self._event_count,
        )


@plugin(
    id="spine.deriver.step_tree",
    provides=("step_tree",),
    layer="L0",
    kind=PluginKind.SEAM,
    description=(
        "Step-tree deriver stub — counts live spine events; full "
        "StepGroupedBackend / journal.json wiring deferred to spine.core."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_deriver_plugins",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Provide a boot-safe ``step_tree`` deriver capability."""
    del config
    deriver = StepTreeDeriverPlugin()
    ctx.provide("step_tree", deriver)
    log.debug("spine.deriver.step_tree: setup complete (stub)")


__all__ = ["StepTreeDeriverPlugin", "setup"]
