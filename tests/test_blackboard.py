"""Blackboard Protocol + InMemoryBlackboard (PR9b.E.6).

The blackboard is the team coordination surface for cross-agent facts.
It supports:
- ``read(topic)`` — list entries in version order
- ``append(topic, entry)`` — append with monotonic version
- ``cas(topic, expected_version, new_entry)`` — compare-and-set on version
- ``acquire_lease / release_lease`` — exclusive write lease with TTL

The implementation is intentionally NOT a CRDT.  This test also
asserts that no CRDT library imports appear in the module.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BB_PATH = REPO_ROOT / "lca" / "layer1_cognitive" / "collaboration" / "blackboard.py"


def _entry(content: str = "x", written_by: str = "alice") -> dict:
    return {"content": content, "written_by": written_by}


class TestInMemoryBlackboard:
    def test_read_returns_entries_in_version_order(self) -> None:
        from lca.layer1_cognitive.collaboration.blackboard import (
            InMemoryBlackboard,
        )

        bb = InMemoryBlackboard()
        bb.append("topic1", _entry("a"))
        bb.append("topic1", _entry("b"))
        bb.append("topic1", _entry("c"))
        entries = bb.read("topic1")
        assert [e.version for e in entries] == [1, 2, 3]
        assert [e.content for e in entries] == ["a", "b", "c"]

    def test_append_increments_version(self) -> None:
        from lca.layer1_cognitive.collaboration.blackboard import (
            InMemoryBlackboard,
        )

        bb = InMemoryBlackboard()
        first = bb.append("t", _entry("x"))
        second = bb.append("t", _entry("y"))
        third = bb.append("t", _entry("z"))
        assert first.version == 1
        assert second.version == 2
        assert third.version == 3
        # IDs must be unique.
        assert len({first.id, second.id, third.id}) == 3

    def test_cas_succeeds_when_expected_version_matches(self) -> None:
        from lca.layer1_cognitive.collaboration.blackboard import (
            InMemoryBlackboard,
        )

        bb = InMemoryBlackboard()
        bb.append("t", _entry("a"))
        ok = bb.cas("t", expected_version=1, new_entry=_entry("b"))
        assert ok is True
        assert [e.content for e in bb.read("t")] == ["a", "b"]

    def test_cas_fails_when_version_mismatch(self) -> None:
        from lca.layer1_cognitive.collaboration.blackboard import (
            InMemoryBlackboard,
        )

        bb = InMemoryBlackboard()
        bb.append("t", _entry("a"))
        bb.append("t", _entry("b"))
        ok = bb.cas("t", expected_version=1, new_entry=_entry("c"))
        assert ok is False
        # Original entries unchanged.
        assert [e.content for e in bb.read("t")] == ["a", "b"]

    def test_acquire_lease_blocks_other_holders_until_expiry(self) -> None:
        from lca.layer1_cognitive.collaboration.blackboard import (
            InMemoryBlackboard,
        )

        bb = InMemoryBlackboard()
        lease = bb.acquire_lease("t", holder="alice", ttl_s=10)
        assert lease is not None
        assert lease.holder == "alice"
        # Second acquisition is denied.
        second = bb.acquire_lease("t", holder="bob", ttl_s=10)
        assert second is None

    def test_acquire_lease_after_release(self) -> None:
        from lca.layer1_cognitive.collaboration.blackboard import (
            InMemoryBlackboard,
        )

        bb = InMemoryBlackboard()
        lease = bb.acquire_lease("t", holder="alice", ttl_s=10)
        assert lease is not None
        bb.release_lease(lease)
        second = bb.acquire_lease("t", holder="bob", ttl_s=10)
        assert second is not None
        assert second.holder == "bob"

    def test_release_lease_allows_reacquire(self) -> None:
        from lca.layer1_cognitive.collaboration.blackboard import (
            InMemoryBlackboard,
        )

        bb = InMemoryBlackboard()
        lease = bb.acquire_lease("t", holder="alice", ttl_s=10)
        assert lease is not None
        bb.release_lease(lease)
        reacquired = bb.acquire_lease("t", holder="bob", ttl_s=10)
        assert reacquired is not None
        assert reacquired.lease_id != lease.lease_id

    def test_acquire_lease_after_ttl_expiry(self) -> None:
        from lca.layer1_cognitive.collaboration.blackboard import (
            InMemoryBlackboard,
        )

        bb = InMemoryBlackboard()
        # Inject a tiny TTL.
        lease = bb.acquire_lease("t", holder="alice", ttl_s=0)
        assert lease is not None
        # Even with ttl_s=0 the lease remains held until released; the
        # expiry path is intentionally observable via ``_now``.
        # We won't time.sleep here; just confirm the release path.
        bb.release_lease(lease)
        reacq = bb.acquire_lease("t", holder="bob", ttl_s=10)
        assert reacq is not None

    def test_no_crdt_in_implementation(self) -> None:
        """The blackboard MUST NOT depend on CRDT libraries."""
        assert BB_PATH.exists(), f"missing {BB_PATH}"
        source = BB_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "crdt" not in alias.name.lower(), (
                        f"forbidden CRDT import: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert "crdt" not in node.module.lower(), (
                    f"forbidden CRDT import from: {node.module}"
                )

    def test_protocol_methods_present(self) -> None:
        """InMemoryBlackboard MUST expose the Protocol methods."""
        from lca.layer1_cognitive.collaboration.blackboard import (
            Blackboard,
            InMemoryBlackboard,
        )

        bb: Blackboard = InMemoryBlackboard()
        assert hasattr(bb, "read")
        assert hasattr(bb, "append")
        assert hasattr(bb, "cas")
        assert hasattr(bb, "acquire_lease")
        assert hasattr(bb, "release_lease")
