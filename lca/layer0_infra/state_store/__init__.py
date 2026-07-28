"""L0 state_store —— StateStore 协议的内置实现（原 state_mgmt/）。"""

from lca.layer0_infra.state_store.in_memory_store import InMemoryStateStore

__all__ = ["InMemoryStateStore"]
