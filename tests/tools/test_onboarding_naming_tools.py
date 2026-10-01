"""Tests for CreateNameWidgetTool and UpdateIdentityTool (INV-03, INV-07)."""

from pathlib import Path

import pytest

from lca.contracts.protocols.assistant.catalog import (
    AssistantCatalog,
    AssistantHandle,
    AssistantSpec,
    PlanRevision,
    ProfilePatch,
)
from lca.contracts.protocols.assistant.ownership import AssistantOwnership
from lca.infrastructure.persistence.user_store import SqliteUserAssistantStore
from lca.infrastructure.tools.onboarding.naming_tools import (
    CREATE_NAME_WIDGET_TOOL,
    UPDATE_IDENTITY_TOOL,
    CreateNameWidgetTool,
    UpdateIdentityTool,
)


class FakeCatalog(AssistantCatalog):
    def __init__(self, tmp_path: Path):
        self.home = tmp_path / "asst_1"
        self.home.mkdir(parents=True, exist_ok=True)
        self.patches: list[ProfilePatch] = []
        self.revision_seq = 1

    def create(self, req):  # type: ignore[no-untyped-def]
        return AssistantHandle("asst_1", str(self.home), 1)

    def get(self, assistant_id: str) -> AssistantSpec:
        raise NotImplementedError

    def list(self, user_id=None):  # type: ignore[no-untyped-def]
        return ()

    def revise_profile(
        self, assistant_id: str, patch: ProfilePatch, actor: str = "system"
    ) -> PlanRevision:
        self.patches.append(patch)
        self.revision_seq += 1
        if patch.user_md is not None:
            (self.home / "USER.md").write_text(patch.user_md, encoding="utf-8")
        if patch.identity_md is not None:
            (self.home / "IDENTITY.md").write_text(patch.identity_md, encoding="utf-8")
        return PlanRevision(
            assistant_id=assistant_id,
            revision_seq=self.revision_seq,
            manifest_digest="sha256:fake",
            actor=actor,
            snapshot_path=str(self.home / f"revisions/{self.revision_seq}.json"),
        )

    def reimport(self, assistant_id: str, reason: str) -> PlanRevision:
        raise NotImplementedError

    def retire(self, assistant_id: str, reason: str) -> None:
        pass


@pytest.fixture
def fake_catalog(tmp_path: Path) -> FakeCatalog:
    return FakeCatalog(tmp_path)


@pytest.fixture
def fake_user_store(tmp_path: Path) -> AssistantOwnership:
    store = SqliteUserAssistantStore(tmp_path / "test.db")
    store.ensure_user("user_123")
    return store


@pytest.mark.asyncio
async def test_create_name_widget_tool_success(
    fake_catalog: FakeCatalog, fake_user_store: AssistantOwnership
):
    tool = CreateNameWidgetTool(
        catalog=fake_catalog,
        assistant_id="asst_1",
        user_store=fake_user_store,
        user_id="user_123",
    )
    assert tool.name == CREATE_NAME_WIDGET_TOOL

    # 1. Validation failure on empty
    obs_fail = await tool.execute({"user_name": ""})
    assert obs_fail.success is False

    # 2. Success path
    obs = await tool.execute({"user_name": "李超"})
    assert obs.success is True
    assert obs.payload is not None
    assert "token" in obs.payload
    assert "candidates" in obs.payload
    assert len(obs.payload["candidates"]) == 2
    assert "[widget:name_picker?token=" in obs.payload["widget_tag"]

    # 3. Assert DB updated (INV-02)
    user_md = fake_user_store.get_user_md("user_123")
    assert user_md is not None
    assert "李超" in user_md

    # 4. Assert Catalog revised Home USER.md (INV-03)
    assert (fake_catalog.home / "USER.md").is_file()
    assert "李超" in (fake_catalog.home / "USER.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_update_identity_tool_success(
    fake_catalog: FakeCatalog, fake_user_store: AssistantOwnership
):
    tool = UpdateIdentityTool(
        catalog=fake_catalog,
        assistant_id="asst_1",
        user_store=fake_user_store,
        user_id="user_123",
    )
    assert tool.name == UPDATE_IDENTITY_TOOL

    # 1. Validation failure on empty
    obs_fail = await tool.execute({"name": ""})
    assert obs_fail.success is False

    # 2. Success path
    obs = await tool.execute({"name": "Athena", "vibe": "敏锐专注", "emoji": "🦉"})
    assert obs.success is True
    assert obs.payload is not None
    assert obs.payload["reaction"] == "🎉"
    assert obs.payload["name"] == "Athena"

    # 3. Assert DB marked completed (INV-01)
    assert fake_user_store.get_onboarding_state("user_123") == "completed"

    # 4. Assert Catalog revised Home IDENTITY.md (INV-03, INV-07)
    identity_file = fake_catalog.home / "IDENTITY.md"
    assert identity_file.is_file()
    content = identity_file.read_text(encoding="utf-8")
    assert "Athena" in content
    assert "敏锐专注" in content
    assert "🦉" in content
