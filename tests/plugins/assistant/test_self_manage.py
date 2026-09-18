"""ADR-0242 PR-5 self-management tests.

Covers:
- ``revise_profile``: SOUL patch → digest change + revision_seq++ + revisions/
  snapshot + ``assistant.profile.revised`` EP; invalid SOUL fail-closed;
  unknown ``extra`` key fail-closed; empty patch fail-closed.
- ``reimport``: recomputes digests and increments revision_seq.
- ``skill_overlay.remove``: removes skill dir + manifest revision + EP.
- Self-management tools: sensitive tools require ``confirmed``; non-sensitive
  tools apply and return a structured payload.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.observability.closure.assistant_ep_closure import (
    ASSISTANT_PROFILE_REVISED,
)
from lca.contracts.protocols.assistant.catalog import (
    CreateAssistantRequest,
    ProfilePatch,
)
from lca.contracts.protocols.assistant.skill_overlay import SkillNotInstalled, SkillSource
from lca.infrastructure.tools.assistant.self_manage_tools import (
    DeleteAssistantSkillTool,
    ListAssistantSkillsTool,
    ListAssistantToolsTool,
    UpdateAssistantGrantsTool,
    UpdateAssistantProfileTool,
    UpdateAssistantSoulTool,
)
from lca.plugins.assistant.skill.overlay import AssistantSkillOverlayImpl
from lca.plugins.domain.assistant.catalog.plugin import (
    AssistantCatalogError,
    AssistantCatalogImpl,
)


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def catalog(tmp_path: Path, emitted: list[tuple[str, dict[str, Any]]]) -> AssistantCatalogImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(root=tmp_path / "assistants", event_emitter=_record)


def _create(catalog: AssistantCatalogImpl, name: str = "测试助理") -> str:
    handle = catalog.create(CreateAssistantRequest(name=name))
    return handle.assistant_id


def _valid_soul() -> str:
    return (
        "## 🧠 身份\n你是数据分析师。\n" * 15
        + "## 🎭 性格\n结论先行。\n" * 15
        + "## 🛠 能力\n擅长 SQL。\n" * 15
        + "## 🗣 语气\n专业务实。\n" * 15
    )


class TestReviseProfile:
    def test_soul_patch_revises_digest_seq_snapshot_and_ep(
        self,
        catalog: AssistantCatalogImpl,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        assistant_id = _create(catalog)
        old_spec = catalog.get(assistant_id)
        old_digest = old_spec.bootstrap.soul_digest
        old_seq = old_spec.revision_seq

        new_soul = _valid_soul()
        revision = catalog.revise_profile(
            assistant_id, ProfilePatch(soul_md=new_soul), actor="agent"
        )

        assert revision.revision_seq == old_seq + 1
        assert revision.actor == "agent"
        new_spec = catalog.get(assistant_id)
        assert new_spec.bootstrap.soul_digest != old_digest
        assert new_spec.revision_seq == old_seq + 1

        home = Path(new_spec.home_path)
        assert (home / "SOUL.md").read_text(encoding="utf-8") == new_soul
        snapshot = home / "revisions" / f"{revision.revision_seq}.json"
        assert snapshot.is_file()

        ep_events = [e for e in emitted if e[0] == ASSISTANT_PROFILE_REVISED]
        assert len(ep_events) == 1
        payload = ep_events[0][1]
        for field in ("assistant_id", "revision_seq", "manifest_digest", "actor"):
            assert field in payload
        assert payload["actor"] == "agent"
        assert "SOUL.md" in payload["changes"]

    @pytest.mark.parametrize(
        "soul",
        [
            "太短",
            "## 🧠 身份\n身份。\n## 🎭 性格\n性格。\n## 🛠 能力\n能力。\n## 🗣 语气\n语气。",
        ],
    )
    def test_invalid_soul_rejected(self, catalog: AssistantCatalogImpl, soul: str) -> None:
        assistant_id = _create(catalog)
        with pytest.raises(AssistantCatalogError, match="SOUL"):
            catalog.revise_profile(assistant_id, ProfilePatch(soul_md=soul))

    def test_unknown_extra_key_rejected(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        with pytest.raises(AssistantCatalogError, match="extra"):
            catalog.revise_profile(assistant_id, ProfilePatch(extra={"bogus": "x"}))

    def test_empty_patch_rejected(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        with pytest.raises(AssistantCatalogError, match="未指定"):
            catalog.revise_profile(assistant_id, ProfilePatch())

    def test_plan_yaml_patch_revises_digest_seq_snapshot_and_ep(
        self,
        catalog: AssistantCatalogImpl,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        """plan.yaml patch：写盘 + digest 重算 + revision_seq++ + revisions 快照 + EP。"""
        assistant_id = _create(catalog)
        old_seq = catalog.get(assistant_id).revision_seq
        old_digest = catalog.get(assistant_id).manifest_digest

        revision = catalog.revise_profile(
            assistant_id,
            ProfilePatch(plan_yaml="prompt:\n  template: react_prompt\n"),
            actor="agent",
        )

        assert revision.revision_seq == old_seq + 1
        home = Path(catalog.get(assistant_id).home_path)
        assert (home / "plan.yaml").read_text(encoding="utf-8") == (
            "prompt:\n  template: react_prompt\n"
        )
        snapshot = home / "revisions" / f"{revision.revision_seq}.json"
        assert snapshot.is_file()

        new_spec = catalog.get(assistant_id)
        assert new_spec.manifest_digest != old_digest
        assert new_spec.plan_overlay is not None
        assert new_spec.plan_overlay.prompt.template == "react_prompt"

        ep_events = [e for e in emitted if e[0] == ASSISTANT_PROFILE_REVISED]
        assert len(ep_events) == 1
        assert "plan.yaml" in ep_events[0][1]["changes"]

    def test_plan_yaml_patch_invalid_fails_closed(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        with pytest.raises(AssistantCatalogError, match=r"plan\.yaml"):
            catalog.revise_profile(assistant_id, ProfilePatch(plan_yaml="prompt:\n  bogus: x\n"))


class TestReimport:
    def test_reimport_recomputes_digests(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        home = Path(catalog.get(assistant_id).home_path)
        (home / "SOUL.md").write_text("被外部工具改写了。\n", encoding="utf-8")

        revision = catalog.reimport(assistant_id, reason="外部修改收编")
        assert revision.actor == "reimport"
        assert revision.revision_seq >= 1

        spec = catalog.get(assistant_id)
        assert spec.bootstrap.soul_digest.startswith("sha256:")
        assert (home / "revisions" / f"{revision.revision_seq}.json").is_file()


class TestSkillOverlayRemove:
    async def test_remove_deletes_skill_and_revises_manifest(
        self,
        catalog: AssistantCatalogImpl,
        emitted: list[tuple[str, dict[str, Any]]],
        tmp_path: Path,
    ) -> None:
        def _record(event: str, payload: Mapping[str, Any]) -> None:
            emitted.append((event, dict(payload)))

        overlay = AssistantSkillOverlayImpl(catalog=catalog, event_emitter=_record)
        assistant_id = _create(catalog)

        pkg = tmp_path / "pkg"
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "SKILL.md").write_text(
            "---\nname: to-remove\ndescription: x\nreferences: []\n---\nbody",
            encoding="utf-8",
        )
        await overlay.install(assistant_id, SkillSource(local_path=str(pkg)))

        home = Path(catalog.get(assistant_id).home_path)
        assert (home / "skills" / "to-remove").is_dir()

        await overlay.remove(assistant_id, "to-remove", actor="agent")
        assert not (home / "skills" / "to-remove").exists()

        ep_events = [e for e in emitted if e[0] == ASSISTANT_PROFILE_REVISED]
        assert any("skills/to-remove" in e[1].get("changes", ()) for e in ep_events)

    async def test_remove_unknown_skill_raises(self, catalog: AssistantCatalogImpl) -> None:
        overlay = AssistantSkillOverlayImpl(catalog=catalog)
        assistant_id = _create(catalog)
        with pytest.raises(SkillNotInstalled):
            await overlay.remove(assistant_id, "nope")


class TestSelfManageTools:
    def test_update_soul_tool_applies(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        tool = UpdateAssistantSoulTool(catalog=catalog, assistant_id=assistant_id)

        obs = asyncio.run(tool.execute({"soul": _valid_soul()}))
        assert obs.success is True
        home = Path(catalog.get(assistant_id).home_path)
        soul_on_disk = (home / "SOUL.md").read_text(encoding="utf-8")
        assert "数据分析师" in soul_on_disk

    def test_update_profile_tool_requires_at_least_one_field(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        assistant_id = _create(catalog)
        tool = UpdateAssistantProfileTool(catalog=catalog, assistant_id=assistant_id)
        obs = asyncio.run(tool.execute({}))
        assert obs.success is False

    def test_delete_skill_requires_confirmation(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        tool = DeleteAssistantSkillTool(catalog=catalog, assistant_id=assistant_id)
        obs = asyncio.run(tool.execute({"skill_id": "x", "confirmed": False}))
        assert obs.success is False
        assert "确认" in (obs.error or "")

    def test_update_grants_requires_confirmation(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        tool = UpdateAssistantGrantsTool(catalog=catalog, assistant_id=assistant_id)
        obs = asyncio.run(tool.execute({"grants_yaml": "grants: []\n", "confirmed": False}))
        assert obs.success is False
        assert "确认" in (obs.error or "")

    def test_list_tools_reads_home_policy(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        tool = ListAssistantToolsTool(catalog=catalog, assistant_id=assistant_id)
        obs = asyncio.run(tool.execute({}))
        assert obs.success is True
        assert isinstance(obs.payload, dict)
        assert "allow" in obs.payload

    def test_list_skills_empty_when_none_installed(self, catalog: AssistantCatalogImpl) -> None:
        assistant_id = _create(catalog)
        overlay = AssistantSkillOverlayImpl(catalog=catalog)
        tool = ListAssistantSkillsTool(catalog=catalog, assistant_id=assistant_id, overlay=overlay)
        obs = asyncio.run(tool.execute({}))
        assert obs.success is True
        assert obs.payload is not None and obs.payload["skills"] == []
