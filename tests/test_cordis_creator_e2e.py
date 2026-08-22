"""Creator four-face end-to-end tests using the real Tool and Composer chain."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from lca.contracts.mechanisms.composition import ComposerErrorCode
from lca.contracts.models.observability.journal import PluginMounted, PluginMountRejected
from lca.layer0_infra.observability.facade import BoundObservability, bind_backends
from lca.layer0_infra.observability.journal_backend import MemoryJournal
from lca.layer4_app.preset_authoring import PresetAuthoring
from lca.plugins.providers.composition_composer import (
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
    from lca.layer0_infra.observability.journal.journal_io import stamped_to_record

    path.write_text(
        "\n".join(
            json.dumps(stamped_to_record(event), ensure_ascii=False)
            for event in journal.store.events
        ),
        encoding="utf-8",
    )


def _plugin_source(name: str, capability: str = "tool_fs.read") -> str:
    return f'''
plugin_meta = {{
    "name": "{name}",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["{capability}"],
    "side_effects": "none",
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
