"""Tests for UserAssistantStore onboarding_state and user_md persistence (INV-01, INV-02)."""

from pathlib import Path

from lca.infrastructure.persistence.user_store import SqliteUserAssistantStore


def test_sqlite_user_store_onboarding_state_and_user_md(tmp_path: Path):
    db_path = tmp_path / "test_lca.sqlite3"
    store = SqliteUserAssistantStore(db_path)

    # 1. ensure_user
    store.ensure_user("u_test_1", username="lichao", email="lichao@example.com")
    assert store.get_onboarding_state("u_test_1") == "pending"
    assert store.get_user_md("u_test_1") is None

    # 2. update_user_md
    sample_md = "# USER.md\n- Name: 李超\n- Role: 系统总架构师\n"
    store.update_user_md("u_test_1", sample_md, display_name="李超")
    assert store.get_user_md("u_test_1") == sample_md

    # 3. set_onboarding_state -> completed (INV-01)
    store.set_onboarding_state("u_test_1", "completed")
    assert store.get_onboarding_state("u_test_1") == "completed"

    # 4. Idempotent check across store reload
    reloaded_store = SqliteUserAssistantStore(db_path)
    assert reloaded_store.get_onboarding_state("u_test_1") == "completed"
    assert reloaded_store.get_user_md("u_test_1") == sample_md
