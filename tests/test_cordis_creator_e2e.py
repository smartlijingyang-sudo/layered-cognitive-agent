"""Creator four-face end-to-end tests using the real Tool and Composer chain."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from lca.application.preset_authoring import PresetAuthoring
from lca.contracts.mechanisms.composition import ComposerErrorCode
from lca.contracts.models.observability.journal import PluginMounted, PluginMountRejected
from lca.infrastructure.observability.facade import BoundObservability, bind_backends
from lca.infrastructure.observability.journal_backend import MemoryJournal
from lca.plugins.providers.think.composition_composer import (
    CordisComposer,
    build_default_invariant_checker,
)
from lca.plugins.tools.cordis_control import build_cordis_control_tool

SCRATCH = Path(__file__).resolve().parent / ".scratch_cordis_creator"
SCRATCH.mkdir(exist_ok=True)


@contextmanager
def bind_journal():
    journal = MemoryJournal()
    with bind_backends(BoundObservability(journal=journal)):
        yield journal


def _dump_journal(journal: MemoryJournal, path: Path) -> None:
    from lca.infrastructure.observability.journal.engine.journal_io import stamped_to_record

    path.write_text(
        "\n".join(
            json.dumps(stamped_to_record(event), ensure_ascii=False)
            for event in journal.store.events
        ),
        encoding="utf-8",
    )


def _plugin_source(
    name: str,
    capability: str = "tool_fs.read",
    side_effects: str = "none",
) -> str:
    return f'''
plugin_meta = {{
    "name": "{name}",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["{capability}"],
    "side_effects": "{side_effects}",
    "policy_class": "execute",
    "test_suite": "tests/test_{name}.py",
}}


def factory():
    import json
    def _keys(text):
        return sorted(json.loads(text).keys())
    return _keys
'''


def _plugin_source_no_meta() -> str:
    return "def factory():\n    return 'ok'\n"


def _new_composer() -> CordisComposer:
    from cordis import Context

    return CordisComposer(Context(), invariant_checker=build_default_invariant_checker())


def _preset_root(name: str) -> Path:
    root = SCRATCH / f"preset_{name}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _tool(composer: CordisComposer, root: Path, grants: tuple[str, ...]):
    return build_cordis_control_tool(
        composer=composer,
        caller_grant=grants,
        actor_role="cordis-creator",
        preset_root=root,
    )


@pytest.fixture
def full_grant() -> tuple[str, ...]:
    return (
        "cordis_control.inspect",
        "cordis_control.author",
        "cordis_control.validate",
        "cordis_control.promote",
        "tool_fs.read",
        "tool_fs.write",
    )


class TestCordisCreatorEnd2End:
    @pytest.mark.asyncio
    async def test_four_faces_publish_plugin_and_make_it_available(self, full_grant) -> None:
        root = _preset_root("happy")
        path = root / "json_keys.py"
        path.write_text(_plugin_source("json_keys"), encoding="utf-8")
        with bind_journal() as journal:
            composer = _new_composer()
            tool = _tool(composer, root, full_grant)
            inspected = await tool.execute({"action": "inspect"})
            authored = await tool.execute(
                {"action": "author", "name": "json_keys", "path": str(path)}
            )
            validated = await tool.execute({"action": "validate", "name": "json_keys"})
            promoted = await tool.execute(
                {
                    "action": "promote",
                    "name": "json_keys",
                    "target_scope": "release",
                    "preset_id": "json_keys",
                }
            )
            assert inspected.success
            assert authored.success and authored.payload["artifact"]["state"] == "draft"
            assert validated.success and validated.payload["artifact"]["state"] == "verified"
            assert promoted.success and promoted.payload["artifact"]["state"] == "active"
            instance = composer._ctx.own_bindings.get("plugin:json_keys")
            assert instance is not None
            assert instance('{"foo": 1, "bar": 2}') == ["bar", "foo"]
            assert PresetAuthoring.list_visible_presets(root=root) == ("json_keys",)
            _dump_journal(journal, SCRATCH / "cordis_creator_run.jsonl")

    @pytest.mark.asyncio
    async def test_experiment_promotion_retains_scope_without_publishing_release(
        self, full_grant
    ) -> None:
        """Experiment promotion stays scoped and cannot create a durable preset."""
        root = _preset_root("experiment_scope")
        path = root / "experiment_only.py"
        path.write_text(_plugin_source("experiment_only"), encoding="utf-8")

        with bind_journal():
            tool = _tool(_new_composer(), root, full_grant)
            assert (
                await tool.execute(
                    {"action": "author", "name": "experiment_only", "path": str(path)}
                )
            ).success
            assert (await tool.execute({"action": "validate", "name": "experiment_only"})).success
            promoted = await tool.execute(
                {
                    "action": "promote",
                    "name": "experiment_only",
                    "target_scope": "experiment",
                }
            )

        assert promoted.success
        assert promoted.payload["target_scope"] == "experiment"
        assert promoted.payload["artifact"]["scope"] == "experiment"
        assert promoted.payload["preset_layout"] is None
        assert PresetAuthoring.list_visible_presets(root=root) == ()

    @pytest.mark.asyncio
    async def test_experiment_promotion_rejects_declared_side_effects(self, full_grant) -> None:
        """The experiment gate fail-closes before mounting an effectful artifact."""
        root = _preset_root("experiment_effect_rejected")
        path = root / "effectful.py"
        path.write_text(_plugin_source("effectful", side_effects="network"), encoding="utf-8")

        with bind_journal() as journal:
            composer = _new_composer()
            tool = _tool(composer, root, full_grant)
            assert (
                await tool.execute({"action": "author", "name": "effectful", "path": str(path)})
            ).success
            assert (await tool.execute({"action": "validate", "name": "effectful"})).success
            rejected = await tool.execute(
                {
                    "action": "promote",
                    "name": "effectful",
                    "target_scope": "experiment",
                }
            )

        assert not rejected.success
        assert rejected.extra["error_code"] == ComposerErrorCode.INVARIANT_VIOLATION.value
        assert composer._ctx.own_bindings.get("plugin:effectful") is None
        mount_rejections = [
            item.event
            for item in journal.store.events
            if isinstance(item.event, PluginMountRejected) and item.event.plugin_name == "effectful"
        ]
        assert len(mount_rejections) == 1
        assert mount_rejections[0].reason_code == ComposerErrorCode.INVARIANT_VIOLATION.value

    @pytest.mark.asyncio
    async def test_promote_with_insufficient_grant_is_rejected(self) -> None:
        root = _preset_root("insufficient_grant")
        path = root / "high_cap.py"
        path.write_text(
            _plugin_source("high_cap", capability="cordis_control.promote"), encoding="utf-8"
        )
        with bind_journal() as journal:
            composer = _new_composer()
            tool = _tool(composer, root, ("tool_fs.read",))
            assert (
                await tool.execute({"action": "author", "name": "high_cap", "path": str(path)})
            ).success
            assert (await tool.execute({"action": "validate", "name": "high_cap"})).success
            result = await tool.execute({"action": "promote", "name": "high_cap"})
            assert not result.success
            assert composer._ctx.own_bindings.get("plugin:high_cap") is None
            rejected = [
                item.event
                for item in journal.store.events
                if isinstance(item.event, PluginMountRejected)
                and item.event.plugin_name == "high_cap"
            ]
            assert len(rejected) == 1
            assert rejected[0].reason_code == ComposerErrorCode.CAPABILITY_GRANT_EXCEEDED.value

    @pytest.mark.asyncio
    async def test_author_requires_valid_plugin_metadata(self, full_grant) -> None:
        root = _preset_root("missing_meta")
        path = root / "no_meta.py"
        path.write_text(_plugin_source_no_meta(), encoding="utf-8")
        with bind_journal():
            result = await _tool(_new_composer(), root, full_grant).execute(
                {"action": "author", "name": "no_meta", "path": str(path)}
            )
        assert not result.success
        assert result.extra["error_code"] == ComposerErrorCode.PLUGIN_META_MISSING.value

    @pytest.mark.asyncio
    async def test_promote_requires_verified_artifact(self, full_grant) -> None:
        root = _preset_root("unverified")
        with bind_journal():
            result = await _tool(_new_composer(), root, full_grant).execute(
                {"action": "promote", "name": "ghost"}
            )
        assert not result.success
        assert "has not been authored" in result.error

    @pytest.mark.asyncio
    async def test_audit_chain_has_creator_events(self, full_grant) -> None:
        root = _preset_root("audit_chain")
        path = root / "json_keys.py"
        path.write_text(_plugin_source("json_keys"), encoding="utf-8")
        with bind_journal() as journal:
            tool = _tool(_new_composer(), root, full_grant)
            assert (await tool.execute({"action": "inspect"})).success
            assert (
                await tool.execute({"action": "author", "name": "json_keys", "path": str(path)})
            ).success
            assert (await tool.execute({"action": "validate", "name": "json_keys"})).success
            assert (await tool.execute({"action": "promote", "name": "json_keys"})).success
            event_types = {item.event_type for item in journal.store.events}
            assert {
                "PluginInspected",
                "PluginAuthored",
                "PluginMounted",
                "RuntimeObserved",
            } <= event_types
            assert "PluginMountRejected" not in event_types
            mounted = [
                item.event for item in journal.store.events if isinstance(item.event, PluginMounted)
            ]
            assert len(mounted) == 1
            assert mounted[0].actor_role == "cordis-creator"
            assert "tool_fs.read" in mounted[0].capabilities
