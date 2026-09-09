"""Invoke a graph worker without agent_lab.nodes.

PR-D deleted ``agent_lab/nodes``. Hosts are builtins (``graph.call`` /
``identity``). Other factories resolve through the Worker registry;
missing execute implementations fail loud instead of importing deleted
modules.
"""

from __future__ import annotations

from typing import Any

from agent_lab.graph.spec import InfoNode
from agent_lab.primitives.artifact import Artifact, ArtifactKind

_HOST = frozenset({"graph.call", "identity", "passthrough__identity"})


def _passthrough(node: InfoNode, inputs: dict[str, Artifact]) -> dict[str, Artifact]:
    empty = Artifact(kind=ArtifactKind.TEXT, content="")
    outs = {port: inputs.get(port, empty) for port in node.outs}
    cfg = node.config or {}
    src = cfg.get("from")
    dst = cfg.get("to")
    if src in inputs and dst in (node.outs or [dst]):
        if dst:
            outs[dst] = inputs[src]
    return outs


def invoke(
    node: InfoNode,
    inputs: dict[str, Artifact],
    seams: Any = None,
) -> dict[str, Artifact]:
    """Dispatch ``node.factory`` to a registered Worker, else host passthrough.

    Registered workers win over the identity/graph.call builtin. Unknown
    non-host factories raise ``KeyError``.
    """
    from lca.plugins.lab.internal.loader import load_all
    from lca.plugins.lab.internal.worker import lookup_worker

    load_all()
    try:
        cls = lookup_worker(node.factory)
    except KeyError:
        if node.factory in _HOST:
            return _passthrough(node, inputs)
        raise
    return cls().execute(node, inputs, seams)
