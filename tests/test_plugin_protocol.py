"""Plugin Protocol 测试 —— 形状 + 模块级 Plugin 兼容。"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.mechanisms.plugin import PluginConfig


class EchoConfig(PluginConfig):
    prefix: str = "hello"


def echo_apply(ctx: object, config: EchoConfig) -> None:
    pass


class TestPluginShape:
    def test_config_is_basemodel(self) -> None:
        assert issubclass(PluginConfig, BaseModel)

    def test_empty_config_instantiates(self) -> None:
        cfg = PluginConfig()
        assert cfg is not None

    def test_subclass_config_validates(self) -> None:
        cfg = EchoConfig(prefix="hi")
        assert cfg.prefix == "hi"

    def test_subclass_config_rejects_unknown_field(self) -> None:
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            EchoConfig(unknown="x")


class EchoPluginModule:
    name = "echo"
    inject: tuple[str, ...] = ()
    provides: str | None = None
    Config = EchoConfig
    apply = staticmethod(echo_apply)


class TestModulePlugin:
    def test_module_has_required_attributes(self) -> None:
        mod = EchoPluginModule()
        assert mod.name == "echo"
        assert mod.inject == ()
        assert mod.provides is None
        assert mod.Config is EchoConfig
        assert callable(mod.apply)

    def test_real_module_like(self) -> None:
        """模块作为 plugin 时通过属性访问，无需实例化。"""
        import types

        mod = types.ModuleType("fake_plugin")
        mod.name = "fake"
        mod.inject = ("tools",)
        mod.provides = "hooks"
        mod.Config = PluginConfig
        mod.apply = lambda ctx, cfg: None

        assert mod.name == "fake"
        assert mod.inject == ("tools",)
        assert mod.provides == "hooks"
