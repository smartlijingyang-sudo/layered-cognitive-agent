"""Tests for AssistantPresetDiscovery and prompt perception injection."""

from __future__ import annotations

from pathlib import Path

from lca.contracts.models.preset.package import AuthoredPlugin, PresetPackage, PresetScope
from lca.contracts.models.team.role.team import RoleProfile, ToolPermissionManifest
from lca.infrastructure.preset.discovery import (
    AssistantPresetDiscovery,
    DiscoveredPreset,
    PresetStatus,
)
from lca.infrastructure.preset.fs_repository import FileSystemPresetRepository
from lca.plugins.prompts.sections import AutonomousPresetsSection


def _sample_plugin(name: str, doc: str = "A sample tool") -> AuthoredPlugin:
    code = f'''
plugin_meta = {{
    "name": "{name}",
    "layer": "behavior",
    "implements": ["Plugin"],
    "capabilities": ["custom.{name}"],
    "side_effects": "none",
    "policy_class": "execute",
    "description": "{doc}",
}}

def factory():
    def {name}(value: int) -> int:
        """{doc}"""
        return value * 2
    return {name}
'''
    return AuthoredPlugin(
        name=name,
        code=code.strip(),
        capabilities=(f"custom.{name}",),
        side_effects="none",
        policy_class="execute",
    )


def test_discover_assistant_presets(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)

    repo = FileSystemPresetRepository()
    plugin = _sample_plugin("aggregator", doc="Aggregate metrics data")
    package = PresetPackage(
        preset_id="data_kit",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        description="Data analytics and aggregation toolkit",
        plugins=(plugin,),
    )
    repo.save(package, assistant_home=assistant_home)

    discovery = AssistantPresetDiscovery(assistant_home=assistant_home, repository=repo)
    discovered = discovery.discover_presets()

    assert len(discovered) == 1
    item: DiscoveredPreset = discovered[0]
    assert item.preset_id == "data_kit"
    assert item.status == PresetStatus.ACTIVE
    assert item.package is not None
    assert item.error_message is None

    # Verify tool materialization
    tools = discovery.discover_tools()
    assert len(tools) == 1
    assert tools[0].name == "aggregator"
    assert "Aggregate metrics data" in tools[0].description


def test_broken_preset_quarantine(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)

    repo = FileSystemPresetRepository()
    # 1. Save healthy preset
    plugin = _sample_plugin("healthy_tool", doc="Healthy tool")
    package = PresetPackage(
        preset_id="healthy_kit",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        description="Healthy toolkit",
        plugins=(plugin,),
    )
    repo.save(package, assistant_home=assistant_home)

    # 2. Inject corrupted preset with broken Python syntax
    broken_dir = assistant_home / "presets" / "broken_kit"
    broken_dir.mkdir(parents=True)
    (broken_dir / "bundle.yaml").write_text("invalid: [yaml: broken", encoding="utf-8")
    plugins_dir = broken_dir / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "syntax_err.py").write_text("def def invalid python syntax !!!", encoding="utf-8")

    # 3. Discover - must NOT crash (INV-RESILIENCE)
    discovery = AssistantPresetDiscovery(assistant_home=assistant_home, repository=repo)
    discovered = discovery.discover_presets()

    assert len(discovered) == 2
    by_id = {d.preset_id: d for d in discovered}

    assert "healthy_kit" in by_id
    assert by_id["healthy_kit"].status == PresetStatus.ACTIVE

    assert "broken_kit" in by_id
    assert by_id["broken_kit"].status == PresetStatus.BROKEN
    assert by_id["broken_kit"].error_message is not None

    # Tools only materialized from healthy preset
    tools = discovery.discover_tools()
    tool_names = [t.name for t in tools]
    assert "healthy_tool" in tool_names
    assert "syntax_err" not in tool_names


def test_prompt_overview_rendering(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)

    repo = FileSystemPresetRepository()
    plugin = _sample_plugin("funnel_calc", doc="Funnel metrics calculator")
    package = PresetPackage(
        preset_id="funnel_kit",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        description="Conversion funnel toolkit",
        plugins=(plugin,),
    )
    repo.save(package, assistant_home=assistant_home)

    discovery = AssistantPresetDiscovery(assistant_home=assistant_home, repository=repo)
    text = discovery.render_prompt_overview()

    assert "## Autonomous Presets & Custom Tools" in text
    assert "funnel_kit" in text
    assert "Conversion funnel toolkit" in text
    assert "funnel_calc" in text
    assert "Funnel metrics calculator" in text


def test_autonomous_presets_section(tmp_path: Path) -> None:
    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)

    repo = FileSystemPresetRepository()
    plugin = _sample_plugin("my_tool", doc="My custom tool")
    package = PresetPackage(
        preset_id="custom_pack",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        description="Custom pack description",
        plugins=(plugin,),
    )
    repo.save(package, assistant_home=assistant_home)

    role_profile = RoleProfile(
        role="arch_assistant",
        goal="testing",
        backstory="testing",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=()),
        extra={"assistant_home_path": str(assistant_home)},
    )

    section = AutonomousPresetsSection()
    output = section.render(
        role_profile=role_profile,
        task="test",
        awareness=None,
        manifest=None,
        tools=(),
        activated_skills=(),
    )

    assert "<autonomous_presets>" in output.text
    assert "custom_pack" in output.text
    assert "my_tool" in output.text


def test_tools_from_scope_includes_discovered_presets(tmp_path: Path) -> None:
    from lca.plugins.transport.webserver.carrier.runs.lifecycle.runnable_assembly import (
        tools_from_scope,
    )

    assistant_home = tmp_path / "assistants" / "asst_arch_01"
    assistant_home.mkdir(parents=True)
    (assistant_home / "tools.yaml").write_text(
        "tools:\n  allow: [base_tool]\n  deny: []\n", encoding="utf-8"
    )
    (assistant_home / "grants.yaml").write_text("grants: []\n", encoding="utf-8")

    # Save a custom preset in assistant_home
    repo = FileSystemPresetRepository()
    plugin = _sample_plugin("auto_gen_tool", doc="Autonomously created tool")
    package = PresetPackage(
        preset_id="auto_kit",
        scope=PresetScope.PRIVATE,
        assistant_id="asst_arch_01",
        description="Autonomous kit",
        plugins=(plugin,),
    )
    repo.save(package, assistant_home=assistant_home)

    class _FakeTool:
        def __init__(self, name: str) -> None:
            self.name = name

    class _FakeMaterializer:
        def __init__(self, tools: list[object]) -> None:
            self._tools = tuple(tools)

        def materialize(self, view: object) -> tuple[object, ...]:
            return self._tools

    class _FakeScope:
        def __init__(self, tools: list[object]) -> None:
            self._tools = _FakeMaterializer(tools)

        def require(self, key: str) -> object:
            if key == "tools":
                return self._tools
            return object()

    scope = _FakeScope([_FakeTool("base_tool")])
    result = tools_from_scope(
        scope,
        None,
        assistant_id="asst_arch_01",
        home_path=str(assistant_home),
    )

    tool_names = [t.name for t in result]
    assert "base_tool" in tool_names
    assert "auto_gen_tool" in tool_names
