"""Adapters — bridge agent_lab artifacts into LCA contracts (one-way).

agent_lab does not modify any LCA source. Adapters live here and translate
between agent_lab primitives (Artifact, ContextManifest) and the LCA
Protocol/DTO contracts the framework already publishes.

MVP: LcaMvProvider bridges agent_lab's model-visible assembly to LCA's
DefaultModelContextAssembler (lca/contracts/protocols/session/model/context.py).
"""

from agent_lab.adapters.lca_mv import LcaMvProvider, SessionReaderAdapter

__all__ = ["LcaMvProvider", "SessionReaderAdapter"]
