"""Harness skill catalog, model tool, slash policy, and audit projection."""

from __future__ import annotations

import asyncio

from lca.contracts.harness.session import SESSION_FORMAT_VERSION, SessionHeader
from lca.harness.projection.registry import InMemoryProjectionRegistry
from lca.harness.session.store import SessionStore
from lca.harness.skills import (
    DiskSkillProvider,
    SkillCatalogService,
    SkillLoadTool,
    SkillSlashActivationPolicy,
    SkillsProjection,
)
from lca.layer0_infra.skills.disk_store import DiskSkillPackageStore
from lca.layer0_infra.skills.settings import SkillSettings


def _store(tmp_path):
    store = DiskSkillPackageStore(SkillSettings(cache_dir=tmp_path / "skills"))
    store.install_package(
        skill_id="reports",
        skill_md_text="---\nname: Reporting\ndescription: Build precise reports\n---\n# Reporting\nUse tables.",
        resource_files={"templates/report.md": b"# Report"},
        source_url="file://reports",
        version="1.2.0",
    )
    return store


def _session() -> SessionStore:
    return SessionStore(
        SessionHeader(version=SESSION_FORMAT_VERSION, id="ses-skills", created_at=0)
    )


def test_disk_provider_catalog_is_summary_only_and_digest_is_stable(tmp_path) -> None:
    provider = DiskSkillProvider(_store(tmp_path))

    async def scenario() -> None:
        first = await provider.snapshot_for("ses-skills")
        second = await provider.snapshot_for("ses-skills")
        assert first.digest == second.digest
        assert first.entries[0].skill_id == "reports"
        assert first.entries[0].description == "Build precise reports"
        assert first.entries[0].resources == ("templates/report.md",)
        assert "Use tables." not in repr(first)

    asyncio.run(scenario())


def test_model_tool_and_user_slash_share_provider_and_write_auditable_facts(tmp_path) -> None:
    catalog = SkillCatalogService(DiskSkillProvider(_store(tmp_path)))
    session = _session()

    async def scenario() -> None:
        await catalog.publish_catalog("ses-skills", session)
        tool = SkillLoadTool(catalog, session_id="ses-skills", events=session)
        result = await tool.execute({"name": "Reporting"})
        assert result.success is True
        assert result.payload["skill_id"] == "reports"
        assert "Use tables." in result.payload["content"]

        slash = SkillSlashActivationPolicy(catalog)
        invocation = await slash.pre_step("ses-skills", "/reports summarize Q2", session)
        assert invocation is not None
        assert invocation.remaining_text == "summarize Q2"
        assert invocation.skill.entry.skill_id == "reports"

    asyncio.run(scenario())
    assert [event.type for event in session.events()] == [
        "skill.catalog.published.v1",
        "skill.loaded.v1",
        "skill.user_invoked.v1",
        "skill.loaded.v1",
        "context.injected.v1",
    ]


def test_skills_projection_replays_durable_facts_without_disk_access(tmp_path) -> None:
    catalog = SkillCatalogService(DiskSkillProvider(_store(tmp_path)))
    session = _session()

    async def scenario() -> None:
        await catalog.publish_catalog("ses-skills", session)
        await SkillSlashActivationPolicy(catalog).pre_step("ses-skills", "/reports", session)

    asyncio.run(scenario())

    projections = InMemoryProjectionRegistry()
    projections.register(SkillsProjection())
    projections.replay("ses-skills", list(session.events()))
    view = projections.snapshot("ses-skills").values["skills"]
    assert view["catalog_digest"]
    assert view["available"][0]["skill_id"] == "reports"
    assert view["loaded"][0]["invocation"] == "user"
    assert view["user_invocations"] == ["reports"]
