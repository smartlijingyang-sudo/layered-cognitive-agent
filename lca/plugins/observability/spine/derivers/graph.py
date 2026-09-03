"""spine.deriver.graph — wraps infrastructure GraphDeriver.

Accumulates execution-point edges and writes a minimal Graphviz
``phase_graph.dot`` on flush / terminal events.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.observability.spine.derivers.graph import GraphDeriver

log = logging.getLogger(__name__)

_DEFAULT_GRAPH_PATH = ".lca/spine/phase_graph.dot"


def _config_path(config: Any) -> Path:
    """Resolve digraph output path from plugin config (dict or object)."""
    if isinstance(config, dict):
        raw = config.get("path", _DEFAULT_GRAPH_PATH)
    else:
        raw = getattr(config, "path", None) or _DEFAULT_GRAPH_PATH
    return Path(str(raw))


@plugin(
    id="spine.deriver.graph",
    provides=("graph",),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="filesystem",
    description=(
        "Graph deriver — accumulates execution_point edges and writes "
        "a minimal Graphviz digraph to phase_graph.dot."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_deriver_plugins",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Provide a ``graph`` deriver capability backed by GraphDeriver."""
    path = _config_path(config)
    deriver = GraphDeriver(output_path=path)
    ctx.provide("graph", deriver)
    log.debug("spine.deriver.graph: setup complete path=%s", path)


__all__ = ["setup"]
