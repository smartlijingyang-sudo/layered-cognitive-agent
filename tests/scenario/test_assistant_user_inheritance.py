"""Tests for AssistantCatalog user profile auto-inheritance (INV-04)."""

from pathlib import Path

from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.infrastructure.persistence.user_store import SqliteUserAssistantStore
from lca.plugins.domain.assistant.catalog.handlers import _AssistantCatalogImpl


def test_create_assistant_inherits_user_md_automatically(tmp_path: Path):
    db_path = tmp_path / "lca.sqlite3"
    user_store = SqliteUserAssistantStore(db_path)
    user_store.ensure_user("u_pro", username="laoli")
    user_store.set_onboarding_state("u_pro", "completed")
    user_md_content = "# USER.md\n\n- **Name:** 老李\n- **Role:** 架构总监\n"
    user_store.update_user_md("u_pro", user_md_content, display_name="老李")

    assistants_root = tmp_path / "assistants"
    catalog = _AssistantCatalogImpl(root=assistants_root, user_store=user_store)

    # 1. Create assistant without seed_user_md -> inherits automatically (INV-04)
    handle = catalog.create(
        CreateAssistantRequest(
            name="ArchAssistant",
            owner_user_id="u_pro",
        )
    )
    spec = catalog.get(handle.assistant_id)
    created_user_md = (Path(spec.home_path) / "USER.md").read_text(encoding="utf-8")
    assert "老李" in created_user_md
    assert "架构总监" in created_user_md


def test_create_assistant_explicit_seed_user_md_wins(tmp_path: Path):
    db_path = tmp_path / "lca.sqlite3"
    user_store = SqliteUserAssistantStore(db_path)
    user_store.ensure_user("u_pro", username="laoli")
    user_store.update_user_md("u_pro", "# USER.md\n- Name: 老李\n")

    assistants_root = tmp_path / "assistants"
    catalog = _AssistantCatalogImpl(root=assistants_root, user_store=user_store)

    # 2. Explicit seed_user_md should NOT be overwritten
    explicit_content = "# USER.md\n\n- **Name:** 特殊别名\n"
    handle = catalog.create(
        CreateAssistantRequest(
            name="SpecialAssistant",
            owner_user_id="u_pro",
            seed_user_md=explicit_content,
        )
    )
    spec = catalog.get(handle.assistant_id)
    created_user_md = (Path(spec.home_path) / "USER.md").read_text(encoding="utf-8")
    assert "特殊别名" in created_user_md
    assert "老李" not in created_user_md
