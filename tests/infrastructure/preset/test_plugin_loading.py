"""Tests for the shared plugin-loading seam (RA-162).

Covers the story's acceptance criteria:
(a) the same .py exec'ed through both pipelines -> one sys.modules entry,
    identical module object, no module-level state fork;
(b) creator line with missing plugin_meta still raises PluginMetaMissing;
(c) discovery line still finds a bare `execute` fallback entry.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from lca.contracts.mechanisms.composition.composition import PluginMetaMissing
from lca.contracts.models.preset.package import AuthoredPlugin
from lca.infrastructure.preset.discovery import AssistantPresetDiscovery
from lca.infrastructure.preset.plugin_loading import (
    load_plugin_module,
    plugin_module_name,
)
from lca.plugins.tools.cordis_control.loader import extract_plugin_factory

_PLUGIN_WITH_META = '''
plugin_meta = {
    "name": "shared_state_probe",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["probe.shared"],
    "side_effects": "none",
    "policy_class": "execute",
    "description": "Probe module-identity convergence",
}

STATE = {"exec_count": 0}
STATE["exec_count"] += 1


def factory():
    """Probe factory."""

    def run_probe() -> dict:
        return {"exec_count": STATE["exec_count"]}

    return run_probe
'''

_NO_META = '''
def factory():
    def run_probe() -> dict:
        return {}
    return run_probe
'''

_BARE_EXECUTE = '''
def execute(payload: dict) -> dict:
    """Bare execute fallback."""
    return {"echo": payload}
'''


def _write_plugin(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source.strip() + "\n", encoding="utf-8")
    return path


def _authored(name: str, code: str) -> AuthoredPlugin:
    return AuthoredPlugin(
        name=name,
        code=code,
        capabilities=("probe.shared",),
        side_effects="none",
        policy_class="execute",
    )


def test_same_path_exec_once_across_pipelines(tmp_path: Path) -> None:
    """(a) Both pipelines loading the same .py -> one exec, one module object."""
    preset_root = tmp_path / "presets"
    plugin_file = preset_root / "shared_state_probe" / "plugins" / "shared_state_probe.py"
    _write_plugin(plugin_file, _PLUGIN_WITH_META)
    source_text = plugin_file.read_text(encoding="utf-8")

    # Creator pipeline first.
    factory, meta = extract_plugin_factory(
        source_path=str(plugin_file),
        source_text=source_text,
        plugin_name="shared_state_probe",
        preset_root=preset_root,
    )
    assert callable(factory)
    assert meta["name"] == "shared_state_probe"

    # Discovery pipeline on the very same path.
    discovery = AssistantPresetDiscovery(assistant_home=tmp_path)
    tool = discovery._load_plugin_tool(
        preset_root / "shared_state_probe",
        _authored("shared_state_probe", source_text),
    )
    assert tool is not None
    assert tool.name == "shared_state_probe"

    # One sys.modules entry, identical module object on both sides.
    module_name = plugin_module_name("shared_state_probe", plugin_file)
    assert module_name in sys.modules
    module = sys.modules[module_name]
    assert load_plugin_module(plugin_file, "shared_state_probe") is module
    # The old dual names never appear: no second exec under a different name.
    assert "lca_agent_presets._runtime.shared_state_probe" not in sys.modules
    assert "lca_presets._autonomous.shared_state_probe.shared_state_probe" not in sys.modules
    # Module-level state was exec'ed exactly once: no forked copies.
    assert module.STATE["exec_count"] == 1


_HOT_V1 = '''
plugin_meta = {
    "name": "hot_probe",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["probe.shared"],
    "side_effects": "none",
    "policy_class": "execute",
    "description": "Hot upgrade probe v1",
}
VERSION = 1


def factory():
    def run_probe() -> dict:
        return {"version": VERSION}

    return run_probe
'''

_HOT_V2 = _HOT_V1.replace("Hot upgrade probe v1", "Hot upgrade probe v2").replace(
    "VERSION = 1", "VERSION = 2"
)


def test_hot_upgrade_reexec_on_content_change(tmp_path: Path) -> None:
    """磁盘内容变化（热升级）时重新 exec：同一路径加载到新版本；内容不变仍复用。"""
    preset_root = tmp_path / "presets"
    preset_dir = preset_root / "hot_probe"
    plugin_file = preset_dir / "plugins" / "hot_probe.py"
    _write_plugin(plugin_file, _HOT_V1)
    discovery = AssistantPresetDiscovery(assistant_home=tmp_path)

    tool_v1 = discovery._load_plugin_tool(
        preset_dir, _authored("hot_probe", plugin_file.read_text(encoding="utf-8"))
    )
    assert tool_v1 is not None
    mod_v1 = load_plugin_module(plugin_file, "hot_probe")
    assert mod_v1.VERSION == 1

    _write_plugin(plugin_file, _HOT_V2)
    tool_v2 = discovery._load_plugin_tool(
        preset_dir, _authored("hot_probe", plugin_file.read_text(encoding="utf-8"))
    )
    assert tool_v2 is not None
    mod_v2 = load_plugin_module(plugin_file, "hot_probe")
    assert mod_v2 is not mod_v1
    assert mod_v2.VERSION == 2

    # 内容不变时再次加载：复用同一对象，不再 exec。
    assert load_plugin_module(plugin_file, "hot_probe") is mod_v2


def test_creator_line_missing_plugin_meta_raises(tmp_path: Path) -> None:
    """(b) PR12 strictness preserved: creator line without plugin_meta raises."""
    preset_root = tmp_path / "presets"
    plugin_file = preset_root / "no_meta_probe" / "plugins" / "no_meta_probe.py"
    _write_plugin(plugin_file, _NO_META)
    with pytest.raises(PluginMetaMissing):
        extract_plugin_factory(
            source_path=str(plugin_file),
            source_text=plugin_file.read_text(encoding="utf-8"),
            plugin_name="no_meta_probe",
            preset_root=preset_root,
        )


@pytest.mark.asyncio
async def test_discovery_line_bare_execute_fallback(tmp_path: Path) -> None:
    """(c) Discovery leniency preserved: a bare `execute` entry is found and works."""
    preset_root = tmp_path / "presets"
    plugin_file = preset_root / "bare_probe" / "plugins" / "bare_probe.py"
    _write_plugin(plugin_file, _BARE_EXECUTE)
    discovery = AssistantPresetDiscovery(assistant_home=tmp_path)
    tool = discovery._load_plugin_tool(
        preset_root / "bare_probe",
        _authored("bare_probe", plugin_file.read_text(encoding="utf-8")),
    )
    assert tool is not None
    assert tool.name == "bare_probe"

    obs = await tool.execute({"payload": {"ping": 1}})
    assert obs.success is True
    assert obs.payload == {"echo": {"ping": 1}}
