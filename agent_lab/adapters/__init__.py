"""Adapters — bridge agent_lab artifacts into LCA contracts (one-way).

Fusion refactor (2026-09-08): this module is being progressively deleted.
Each adapter that becomes redundant (LCA module directly importable via
`uv run`) is removed and its node plugin imports LCA directly instead.

Currently retained:
  - mv.assemble adapter (lca_mv.py) — will be removed next
  - call_llm adapter (lca_llm.py) — will be removed next
  - read_file Tool (adapters/tools/read_file.py) — agent_lab's own Tool

Removed:
  - lca_body.py — dispatch_tool now imports SimpleSafeExecutor directly
"""

# Temporary re-exports kept until lca_mv / lca_llm are also removed.
from agent_lab.adapters.lca_llm import LcaLlmProvider
from agent_lab.adapters.lca_mv import LcaMvProvider, SessionReaderAdapter

__all__ = [
    "LcaLlmProvider",
    "LcaMvProvider",
    "SessionReaderAdapter",
]
