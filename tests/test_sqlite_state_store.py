"""Tests for durable StateStore selection and SQLite checkpoint persistence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.journal.spec import STATE_STORE_CHOICE_PROFILE_DEFAULT
from lca.harness.profile.source import load_profile_source
from lca.infrastructure.capability.state_store import StateStoreService
from lca.infrastructure.state_store.in_memory_store import InMemoryStateStore
from lca.infrastructure.state_store.sqlite_store import SqliteStateStore
from lca.plugins.composer.internal.perceive import resolve_state_store
from lca.plugins.providers.state import state_store as state_store_provider


@pytest.mark.asyncio
async def test_sqlite_state_store_recovers_complete_state_across_instances(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "agent-state.db"
    state = AgentState(
        trace_id="trace-persistent",
        task="test durable resume",
        budget=Budget(max_steps=8, used_steps=3),
        working_memory={"hypothesis": "persist this"},
        retrieved_context=[{"source": "paper-1"}],
        step=3,
        extra={"artifact_ref": "artifact://experiment/1"},
    )

    state_ref = await SqliteStateStore(database_path).save(state)
    restored = await SqliteStateStore(database_path).load(state_ref)

    assert state_ref == "sqlite://trace-persistent/3"
    assert restored is not state
    assert restored == state


@pytest.mark.asyncio
async def test_sqlite_state_store_rejects_corrupt_payload(tmp_path: Path) -> None:
    database_path = tmp_path / "agent-state.db"
    state = AgentState(trace_id="trace-corrupt", task="detect corruption", budget=Budget())
    store = SqliteStateStore(database_path)
    state_ref = await store.save(state)

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "UPDATE agent_state_snapshots SET payload = ? WHERE state_ref = ?",
            (sqlite3.Binary(b"corrupt"), state_ref),
        )

    with pytest.raises(ValueError, match="digest mismatch"):
        await store.load(state_ref)


@dataclass
class _PluginContext:
    services: dict[str, object]

    def require(self, key: str) -> object:
        return self.services[key]


@pytest.mark.asyncio
async def test_profile_default_state_store_uses_active_sqlite_provider(tmp_path: Path) -> None:
    service = StateStoreService()
    context = _PluginContext({"state_store": service})

    await state_store_provider.setup.setup(
        context,
        state_store_provider.Config(
            providers=["memory", "sqlite"],
            active_provider="sqlite",
            sqlite_database_path=str(tmp_path / "profile-state.db"),
        ),
    )

    selected = resolve_state_store(STATE_STORE_CHOICE_PROFILE_DEFAULT, service)
    explicit_memory = resolve_state_store("memory", service)

    assert isinstance(selected, SqliteStateStore)
    assert isinstance(explicit_memory, InMemoryStateStore)
    assert service.providers.active == "sqlite"


def test_continuous_profile_enables_sqlite_state_and_control_plane() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    profile = load_profile_source(repository_root / "profiles" / "web-standard-continuous.yaml")
    entries = {str(entry["id"]): entry for entry in profile.entries}

    assert "bundles/continuous-control-plane.yaml" in profile.bundles
    assert entries["lca-state-store-provider"]["config"] == {
        "providers": ["memory", "sqlite"],
        "active_provider": "sqlite",
        "sqlite_database_path": ".lca/agent-state.db",
    }
