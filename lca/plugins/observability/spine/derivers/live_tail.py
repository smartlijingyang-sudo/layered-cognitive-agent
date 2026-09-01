"""spine.deriver.live_tail — wraps infrastructure LiveTailDeriver.

``LiveTail`` is zero-arg constructible, so this plugin boots a real
ring-buffer deriver without webserver dependencies. SSE subscription
wiring remains optional for later transport composition.
"""

from __future__ import annotations

import logging
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.journal.stream.live_tail import LiveTail
from lca.infrastructure.observability.spine.derivers.live_tail import LiveTailDeriver

log = logging.getLogger(__name__)


@plugin(
    id="spine.deriver.live_tail",
    provides=("live_tail",),
    layer="L0",
    kind=PluginKind.SEAM,
    description=(
        "Live-tail deriver — wraps LiveTail ring buffer as a spine "
        "Deriver; SSE fan-out is available via subscribe()."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_deriver_plugins",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Provide a ``live_tail`` deriver capability backed by LiveTailDeriver."""
    del config
    deriver = LiveTailDeriver(tail=LiveTail())
    ctx.provide("live_tail", deriver)
    log.debug("spine.deriver.live_tail: setup complete")


__all__ = ["setup"]
