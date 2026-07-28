"""兼容 shim —— 请改用 ``lca.layer0_infra.state_store``（ADR-0016）。"""

from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore

__all__ = ["InMemoryStateStore"]
