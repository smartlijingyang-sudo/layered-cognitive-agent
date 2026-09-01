"""spine.deriver.narrative — wraps infrastructure NarrativeDeriver.

``StepNarrativeWriter`` only needs an output path, so this plugin can
construct a real ``NarrativeDeriver`` at boot without journal backends.
``on_event`` remains document-driven (debug log only); ``write_document``
is available once a ``JournalDocument`` exists.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.journal.step.narrative_writer import (
    StepNarrativeWriter,
)
from lca.infrastructure.observability.spine.derivers.narrative import NarrativeDeriver

log = logging.getLogger(__name__)

_DEFAULT_NARRATIVE_PATH = ".lca/spine/journal.narrative.md"


def _config_path(config: Any) -> Path:
    """Resolve narrative output path from plugin config (dict or object)."""
    if isinstance(config, dict):
        raw = config.get("path", _DEFAULT_NARRATIVE_PATH)
    else:
        raw = getattr(config, "path", None) or _DEFAULT_NARRATIVE_PATH
    return Path(str(raw))


@plugin(
    id="spine.deriver.narrative",
    provides=("narrative",),
    layer="L0",
    kind=PluginKind.SEAM,
    description=(
        "Narrative deriver — wraps StepNarrativeWriter / NarrativeDeriver; "
        "on_event is a no-op log; write_document renders journal.narrative.md."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_deriver_plugins",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Provide a ``narrative`` deriver capability backed by NarrativeDeriver."""
    path = _config_path(config)
    writer = StepNarrativeWriter(path)
    deriver = NarrativeDeriver(writer=writer)
    ctx.provide("narrative", deriver)
    log.debug("spine.deriver.narrative: setup complete path=%s", path)


__all__ = ["setup"]
