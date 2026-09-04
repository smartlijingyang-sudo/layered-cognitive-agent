"""Harness skill catalog, model tool, slash policy, and audit projection."""

from __future__ import annotations

import asyncio

from lca.contracts.harness.memory.events import SkillRouted
from lca.contracts.harness.tasks.session import SESSION_FORMAT_VERSION, SessionHeader
from lca.harness.projection.registry import InMemoryProjectionRegistry
from lca.harness.session.store import SessionStore
from lca.harness.skills import (
    DiskSkillProvider,
    SkillCatalogService,
    SkillLoadTool,
    SkillSlashActivationPolicy,
    SkillsProjection,
)
from lca.infrastructure.skills.disk_store import DiskSkillPackageStore
from lca.infrastructure.skills.settings import SkillSettings


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
        "skill.activated.v1",
        "skill.user_invoked.v1",
        "skill.loaded.v1",
        "skill.activated.v1",
        "context.injected.v1",
    ]
    activated = [event for event in session.events() if event.type == "skill.activated.v1"]
    assert [event.data["source"] for event in activated] == ["skill_tool", "slash:/skill"]


def test_user_slash_activation_loads_once_through_catalog_seam(tmp_path) -> None:
    class CountingProvider(DiskSkillProvider):
        def __init__(self, store) -> None:
            super().__init__(store)
            self.load_count = 0

        async def load(self, name: str, session_id: str):
            self.load_count += 1
            return await super().load(name, session_id)

    provider = CountingProvider(_store(tmp_path))
    catalog = SkillCatalogService(provider)
    session = _session()

    async def scenario() -> None:
        invocation = await SkillSlashActivationPolicy(catalog).pre_step(
            "ses-skills", "/reports summarize Q2", session
        )
        assert invocation is not None
        assert invocation.skill.entry.skill_id == "reports"

    asyncio.run(scenario())
    assert provider.load_count == 1
    assert [event.type for event in session.events()] == [
        "skill.user_invoked.v1",
        "skill.loaded.v1",
        "skill.activated.v1",
        "context.injected.v1",
    ]


def test_skills_projection_replays_durable_facts_without_disk_access(tmp_path) -> None:
    catalog = SkillCatalogService(DiskSkillProvider(_store(tmp_path)))
    session = _session()

    async def scenario() -> None:
        await catalog.publish_catalog("ses-skills", session)
        await SkillSlashActivationPolicy(catalog).pre_step("ses-skills", "/reports", session)
        await session.append(
            SkillRouted(template_id="research_prompt", decision_path="keyword_match"),
            actor="system",
        )

    asyncio.run(scenario())

    projections = InMemoryProjectionRegistry()
    projections.register(SkillsProjection())
    projections.replay("ses-skills", list(session.events()))
    view = projections.snapshot("ses-skills").values["skills"]
    assert view["catalog_digest"]
    assert view["available"][0]["skill_id"] == "reports"
    assert view["loaded"][0]["invocation"] == "user"
    assert view["user_invocations"] == ["reports"]

    (activated,) = view["activated"]
    assert activated["skill_id"] == "reports"
    assert activated["name"] == "Reporting"
    assert activated["content_hash"] == view["loaded"][0]["content_hash"]
    assert activated["activated_at_step"] == 0
    assert activated["source"] == "slash:/skill"

    (routed,) = view["routed"]
    assert routed["template_id"] == "research_prompt"
    assert routed["decision_path"] == "keyword_match"
    assert routed["source"] == "skill_router"
    assert routed["seq"] == session.events()[-1].seq


def test_model_tool_load_emits_paired_loaded_and_activated_facts(tmp_path) -> None:
    catalog = SkillCatalogService(DiskSkillProvider(_store(tmp_path)))
    session = _session()

    async def scenario() -> None:
        tool = SkillLoadTool(catalog, session_id="ses-skills", events=session)
        result = await tool.execute({"name": "Reporting"})
        assert result.success is True

    asyncio.run(scenario())
    events = session.events()
    assert [event.type for event in events] == ["skill.loaded.v1", "skill.activated.v1"]
    activated = events[1]
    assert activated.visibility == "audit"
    assert activated.actor == "agent"
    assert activated.data["skill_id"] == "reports"
    assert activated.data["name"] == "Reporting"
    assert activated.data["content_hash"] == events[0].data["content_hash"]
    assert activated.data["activated_at_step"] == 0
    assert activated.data["source"] == "skill_tool"


def test_model_tool_load_failure_emits_no_activation_fact(tmp_path) -> None:
    catalog = SkillCatalogService(DiskSkillProvider(_store(tmp_path)))
    session = _session()

    async def scenario() -> None:
        tool = SkillLoadTool(catalog, session_id="ses-skills", events=session)
        result = await tool.execute({"name": "missing"})
        assert result.success is False

    asyncio.run(scenario())
    assert session.events() == ()
