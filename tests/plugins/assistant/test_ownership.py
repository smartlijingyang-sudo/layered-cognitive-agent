"""assistant.ownership —— LCA 自有数据库归属关系（ADR-0252 PR-2）。

覆盖 ``SqliteUserAssistantStore`` 的 CRUD/幂等语义与插件 setup 安装
``app.state.assistant_ownership`` 的行为。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lca.contracts.protocols.assistant.ownership import UserAssistantBinding
from lca.infrastructure.persistence.user_store import SqliteUserAssistantStore


def _binding(
    *,
    user_id: str = "user_1",
    assistant_id: str = "asst_1",
    client_id: str = "client_1",
    **kwargs: object,
) -> UserAssistantBinding:
    return UserAssistantBinding(
        user_id=user_id,
        assistant_id=assistant_id,
        client_id=client_id,
        **kwargs,
    )


@pytest.fixture()
def store(tmp_path) -> SqliteUserAssistantStore:
    return SqliteUserAssistantStore(path=tmp_path / "lca.sqlite3")


def test_ensure_user_and_onboarding_state(store: SqliteUserAssistantStore) -> None:
    store.ensure_user("user_1", username="alice", email="alice@example.com")
    assert store.get_onboarding_state("user_1") == "pending"
    store.set_onboarding_state("user_1", "completed")
    assert store.get_onboarding_state("user_1") == "completed"


def test_get_onboarding_state_unknown_user_defaults_pending(
    store: SqliteUserAssistantStore,
) -> None:
    assert store.get_onboarding_state("nobody") == "pending"


def test_bind_owner_of_and_list(store: SqliteUserAssistantStore) -> None:
    store.ensure_user("user_1")
    store.bind(_binding())
    assert store.owner_of("asst_1") == "user_1"
    assert store.assistant_ids_for("user_1") == ("asst_1",)


def test_bind_is_idempotent_on_client_id(store: SqliteUserAssistantStore) -> None:
    store.ensure_user("user_1")
    store.bind(_binding())
    # Same client_id again → no-op, no second row, same assistant.
    store.bind(_binding())
    assert store.assistant_ids_for("user_1") == ("asst_1",)
    assert store.owner_of("asst_1") == "user_1"


def test_bind_same_assistant_different_client_no_duplicate(
    store: SqliteUserAssistantStore,
) -> None:
    store.ensure_user("user_1")
    store.bind(_binding(client_id="client_1"))
    store.bind(_binding(client_id="client_2"))
    assert store.assistant_ids_for("user_1") == ("asst_1",)


def test_set_agent_id(store: SqliteUserAssistantStore) -> None:
    store.ensure_user("user_1")
    store.bind(_binding())
    assert store.agent_id_of("asst_1") is None
    store.set_agent_id("asst_1", "agt_1")
    assert store.agent_id_of("asst_1") == "agt_1"


def test_agent_id_unique_index(store: SqliteUserAssistantStore) -> None:
    import sqlite3

    store.ensure_user("user_1")
    store.ensure_user("user_2")
    store.bind(_binding(assistant_id="asst_1", client_id="client_1"))
    store.set_agent_id("asst_1", "agt_1")
    store.bind(_binding(assistant_id="asst_2", client_id="client_2"))
    with pytest.raises(sqlite3.IntegrityError):
        # Same agent_id bound to a second assistant violates the unique index.
        store.set_agent_id("asst_2", "agt_1")


def test_list_orders_by_created_at(store: SqliteUserAssistantStore) -> None:
    store.ensure_user("user_1")
    store.bind(_binding(assistant_id="asst_b", client_id="client_b"))
    store.bind(_binding(assistant_id="asst_a", client_id="client_a"))
    assert set(store.assistant_ids_for("user_1")) == {"asst_a", "asst_b"}


# ── 插件 setup ───────────────────────────────────────────────────────


class _FakeAppState:
    def __init__(self) -> None:
        self.state = _FakeState()


class _FakeState:
    assistant_ownership = None


class _FakeWebServer:
    def __init__(self) -> None:
        self.app = _FakeAppState()


class _FakeCtx:
    def __init__(self, server: _FakeWebServer) -> None:
        self._server = server
        self._provided: dict[str, object] = {}

    def require(self, key: str) -> object:
        assert key == "web_server"
        return self._server

    def provide(self, key: str, value: object) -> None:
        self._provided[key] = value


@pytest.mark.asyncio
async def test_setup_installs_app_state() -> None:
    from lca.plugins.assistant.ownership.plugin import Config
    from lca.plugins.assistant.ownership.plugin import setup as plugin

    server = _FakeWebServer()
    ctx = _FakeCtx(server)
    await plugin.setup(ctx, Config())
    assert ctx._provided["assistant.ownership"] is not None
    assert server.app.state.assistant_ownership is not None


def test_config_rejects_unknown_fields() -> None:
    from lca.plugins.assistant.ownership.plugin import Config

    with pytest.raises(ValidationError):
        Config(unknown_field=1)  # type: ignore[call-arg]
