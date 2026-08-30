"""Sensor v3 plugin tests (PR13 / PR14).

Two new sensors land in this slice:

- ``WorkspaceInstructionsSensor`` (named factory ``sensor.workspace-instructions``)
  reads ``AGENTS.md`` (path from settings; default ``./AGENTS.md``) and
  emits a ``workspace_instructions`` ``ContextItem``.  Missing file is a
  no-op (empty manifest).

- ``SkillCatalogSensor`` (named factory ``sensor.skill-catalog``) reads
  the visible skill list from the operational-skill store and emits a
  ``skill_catalog`` ``ContextItem`` (list[dict]).

The default ``source`` of ``SkillCatalogPublished`` shifts from
``pre_step`` to ``perceive`` to reflect that the catalog is now a
manifest item, not a pre-step hook.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.operational_skills import (
    SkillIndexEntry,
)


def _state() -> AgentState:
    return AgentState(trace_id="t", task="x", budget=Budget(max_steps=5), step=0)


class TestWorkspaceInstructionsSensor:
    async def test_workspace_instructions_sensor_reads_agents_md(self, tmp_path: Path) -> None:
        """The sensor MUST read AGENTS.md and emit its content as payload."""
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("Hello from AGENTS.md\n", encoding="utf-8")

        from lca.layer1_cognitive.sensors.workspace_instructions import (
            WorkspaceInstructionsSensor,
        )

        sensor = WorkspaceInstructionsSensor(path=agents_md)
        items = await sensor.read(_state())
        assert items, "sensor must emit at least one ContextItem"
        item = items[0]
        assert item.kind == "workspace_instructions"
        assert "Hello from AGENTS.md" in (item.payload or "")

    async def test_workspace_instructions_sensor_missing_file_returns_empty(
        self, tmp_path: Path
    ) -> None:
        """A missing AGENTS.md MUST yield zero items, not an exception."""
        from lca.layer1_cognitive.sensors.workspace_instructions import (
            WorkspaceInstructionsSensor,
        )

        missing = tmp_path / "does_not_exist.md"
        sensor = WorkspaceInstructionsSensor(path=missing)
        items = await sensor.read(_state())
        assert items == []

    async def test_workspace_instructions_named_factory_exists(self) -> None:
        """``build_workspace_instructions_sensor`` MUST be exposed."""
        from lca.layer1_cognitive.sensors.workspace_instructions import (
            build_workspace_instructions_sensor,
        )

        sensor = build_workspace_instructions_sensor()
        # Should be a Sensor (has read()).
        assert hasattr(sensor, "read")


class TestSkillCatalogSensor:
    async def test_skill_catalog_sensor_lists_registry(self) -> None:
        """The sensor MUST emit a ``skill_catalog`` item from the registry."""

        class _StubStore:
            def list_installed(self) -> tuple[SkillIndexEntry, ...]:
                return (
                    SkillIndexEntry(
                        skill_id="a",
                        name="alpha",
                        summary="first",
                    ),
                    SkillIndexEntry(
                        skill_id="b",
                        name="beta",
                        summary="second",
                    ),
                )

        from lca.layer1_cognitive.sensors.skill_catalog import (
            build_skill_catalog_sensor,
        )

        sensor = build_skill_catalog_sensor(_StubStore())  # type: ignore[arg-type]
        items = await sensor.read(_state())
        assert items
        item = items[0]
        assert item.kind == "skill_catalog"
        assert isinstance(item.payload, list)
        skill_ids = {entry["skill_id"] for entry in item.payload}
        assert skill_ids == {"a", "b"}

    async def test_skill_catalog_sensor_empty_registry(self) -> None:
        """Empty registry MUST emit an empty list (no item)."""

        class _EmptyStore:
            def list_installed(self) -> tuple[SkillIndexEntry, ...]:
                return ()

        from lca.layer1_cognitive.sensors.skill_catalog import (
            build_skill_catalog_sensor,
        )

        sensor = build_skill_catalog_sensor(_EmptyStore())  # type: ignore[arg-type]
        items = await sensor.read(_state())
        # No skills → nothing to advertise; sensor skips the emit.
        assert items == []


class TestSkillCatalogPublishedSource:
    def test_skill_catalog_published_source_default_perceive(self) -> None:
        """``SkillCatalogPublished.source`` default MUST be ``"perceive"``."""
        from lca.contracts.harness.events import SkillCatalogPublished

        evt = SkillCatalogPublished(entries=(), digest="")
        assert evt.source == "perceive"
