"""插件 Manifest 公开门面与内部接缝的架构回归测试。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from lca.harness.plugin_api import (
    EffectClass,
    PluginContext,
    PluginDefinition,
    PluginKind,
    definition_from_plugin,
    plugin,
)
from lca.harness.plugin_context import AuditedPluginContext
from lca.harness.plugin_declaration import PluginCarrier
from lca.harness.plugin_manifest import PluginDefinition as ManifestPluginDefinition


class _Config(BaseModel):
    enabled: bool = True


async def _setup(_ctx: PluginContext, _config: _Config) -> None:
    return None


def test_public_plugin_api_preserves_the_manifest_identity_and_decorator_round_trip() -> None:
    """插件只依赖稳定门面，装饰器仍产生同一不可变 Manifest 事实。"""

    carrier = plugin(
        id="test.plugin-manifest-facade",
        Config=_Config,
        provides=("test.capability",),
        requires=("test.dependency",),
        layer="L1",
        kind=PluginKind.PROVIDER,
        effects=EffectClass.NONE,
        test_suite=__name__,
    )(_setup)

    definition = definition_from_plugin(carrier)

    assert PluginDefinition is ManifestPluginDefinition
    assert definition.spec.id == "test.plugin-manifest-facade"
    assert definition.Config is _Config
    assert definition.provided_capability_keys == ("test.capability",)
    assert definition.required_capability_keys == ("test.dependency",)
    assert definition.setup is _setup


def test_public_plugin_api_retains_runtime_audit_and_carrier_types() -> None:
    """运行期审计与 Cordis 载体适配继续通过同一公开入口可发现。"""

    assert AuditedPluginContext.__module__ == "lca.harness.plugin_context"
    assert PluginCarrier.__module__ == "lca.harness.plugin_declaration"


def test_plugin_api_is_a_thin_stable_facade() -> None:
    """公开门面不重新实现声明、载体适配或运行期审计行为。"""

    source = (Path(__file__).resolve().parents[2] / "lca" / "harness" / "plugin_api.py").read_text(
        encoding="utf-8"
    )

    assert "class " not in source
    assert "def " not in source
    assert "plugin_manifest" in source
    assert "plugin_declaration" in source
    assert "plugin_context" in source
