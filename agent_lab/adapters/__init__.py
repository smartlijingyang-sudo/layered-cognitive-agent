"""Adapters — bridge agent_lab artifacts into LCA contracts (one-way).

agent_lab does not modify any LCA source. Adapters live here and translate
between agent_lab primitives (Artifact, ContextManifest) and the LCA
Protocol/DTO contracts the framework already publishes.

Seams wired so far:
  - mv.assemble ↔ DefaultModelContextAssembler (lca_mv.py)
  - tool dispatch ↔ SimpleSafeExecutor (lca_body.py)
  - call_llm ↔ LLMAdapter Protocol (lca_llm.py)
  - read_file Tool (adapters/tools/read_file.py) — agent_lab's own Tool
"""

from agent_lab.adapters.lca_body import LcaBodyProvider
from agent_lab.adapters.lca_llm import LcaLlmProvider
from agent_lab.adapters.lca_mv import LcaMvProvider, SessionReaderAdapter

__all__ = [
    "LcaBodyProvider",
    "LcaLlmProvider",
    "LcaMvProvider",
    "SessionReaderAdapter",
]
