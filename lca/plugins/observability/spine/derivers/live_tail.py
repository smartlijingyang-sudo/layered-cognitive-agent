"""spine.deriver.live_tail — wraps infrastructure LiveTailDeriver.

``LiveTail`` is zero-arg constructible, so this plugin boots a real
ring-buffer capability without webserver dependencies. ``subscribe()``
on the deriver is SSE carrier fan-out (LiveTail passthrough), not an
EventSpine.subscribe fold path (I-SESSION-5 / ADR-0186 PR-3g).
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
    effects="none",
    description=(
        "Live-tail SSE carrier — wraps LiveTail ring buffer; "
        "subscribe() is transport fan-out, not EventSpine fold derivation."
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
