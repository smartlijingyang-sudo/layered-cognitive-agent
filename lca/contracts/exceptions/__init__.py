"""Contract-layer exception families (ADR-0217 §3.3.1 / ADR-0015).

Closed sets: subgraph recursion failures (``subgraph.py``) and the registry
key lookup error (``registry.py``). Each subclass carries identifying
attributes so callers can inspect without re-parsing the message. Stays
dependency-free per ADR-0015 + AGENTS.md §2.1 — leaf.
"""

from lca.contracts.exceptions.registry import RegistryKeyError

__all__ = ["RegistryKeyError"]
