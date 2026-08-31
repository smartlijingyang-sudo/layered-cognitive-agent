from __future__ import annotations

from lca.cognition.memory.team_shared_memory import TeamSharedMemoryStore
from lca.contracts.atoms.enums import MemoryLayer


def test_team_shared_memory_exposes_scope() -> None:
    store = TeamSharedMemoryStore(
        [MemoryLayer.SEMANTIC],
        tenant_id="tenant-a",
        session_scope="team-1",
    )

    assert store.scope == ("tenant-a", "team-1")
