"""美食广场的入驻规章制度。

本模块验证「共享美食广场」里所有参与者必须遵守的基本制度：

- **PluginConfig（档口入驻登记表）**：每个入驻档口必须在管理处登记自己的名字、
  依赖项、提供的服务。表格格式严格——多填一行都会被退回。
- **Plugin Protocol（档口资质模板）**：入驻档口要么是一个类，要么是一个模块，
  但必须凑齐五样资质——name、inject、provides、Config、apply。
- **SeamRole（能力三角）**：一项完整的能力由三种角色构成——
  菜单定义（DEFINITION）、厨师实现（PROVIDER）、食客消费（CONSUMER）。
- **SeamRegistry（能力验证处）**：管理处随时可以查验某项能力是否三角齐全。
- **consume gate（组合期门）**：只有登记过的食客才能领取厨师的菜——
  未经注册的消费者会被拦截。
- **require_complete（开业前检查）**：宣布某项能力「就绪」之前，必须三角到位。
- **SeamKey（能力目录枚举）**：广场常驻的能力门类清单。
- **@seam 装饰器（能力标签贴）**：给类贴上「我是某能力的某角色」标签。
"""

from __future__ import annotations

from typing import Any, Protocol

import pytest
from pydantic import BaseModel, ValidationError

from lca.contracts.mechanisms.capability import REQUIRED_SEAM_KEYS, MissingCapabilityError, SeamKey
from lca.contracts.mechanisms.plugin import Plugin, PluginConfig
from lca.contracts.mechanisms.seam import (
    IncompleteSeamError,
    SeamDeclaration,
    SeamRegistry,
    SeamRole,
    UnauthorizedConsumerError,
    consume,
    get_global_seam_registry,
    require_complete,
    seam,
)

# ── PluginConfig ────────────────────────────────────────────


class TestPluginConfig:
    """档口入驻登记表的格式校验——多一个字段都不行。"""

    def test_is_basemodel_subclass(self) -> None:
        """登记表本身是 pydantic BaseModel 家族出身。"""
        assert issubclass(PluginConfig, BaseModel)

    def test_empty_config_instantiates(self) -> None:
        """空配置可以入驻——没有额外要求。"""
        cfg = PluginConfig()
        assert cfg is not None

    def test_extra_field_rejected(self) -> None:
        """管理处不收多余的字段——乱填一律退回。"""
        with pytest.raises(ValidationError):
            PluginConfig(bogus="nope")

    def test_subclass_with_fields(self) -> None:
        """档口可以在标准表格上扩展自己的字段。"""

        class MyConfig(PluginConfig):
            prefix: str = "hello"
            count: int = 0

        cfg = MyConfig(prefix="hi", count=3)
        assert cfg.prefix == "hi"
        assert cfg.count == 3

    def test_subclass_still_forbids_extra(self) -> None:
        """扩展了字段也不能乱填——依然是严格模式。"""

        class StrictConfig(PluginConfig):
            value: int = 1

        with pytest.raises(ValidationError):
            StrictConfig(extra_field="bad")

    def test_model_config_extra_is_forbid(self) -> None:
        """登记表底层写死了 extra='forbid'——多填就报错。"""
        assert PluginConfig.model_config["extra"] == "forbid"


# ── Plugin Protocol shape ───────────────────────────────────


class TestPluginProtocolShape:
    """档口资质模板——不管是类还是模块，必须凑齐五样资质。"""

    def test_is_runtime_checkable(self) -> None:
        """Plugin 是 @runtime_checkable 的——运行时也能 isinstance 验明正身。"""

        class FakePlugin:
            name = "fake"
            inject: tuple[str, ...] = ()
            provides: str | None = None
            Config = PluginConfig

            def apply(self, ctx: Any, config: PluginConfig) -> None:
                pass

        assert isinstance(FakePlugin(), Plugin)

    def test_missing_attribute_fails_isinstance(self) -> None:
        """缺了资质就过不了关——isinstance 直接返回 False。"""

        class Incomplete:
            name = "x"
            # missing inject, provides, Config, apply

        assert not isinstance(Incomplete(), Plugin)

    def test_module_level_attributes(self) -> None:
        """模块也能当档口——只要顶层摆齐五样资质。"""
        import types

        mod = types.ModuleType("fake_mod_plugin")
        mod.name = "mod_plugin"
        mod.inject = ("tools",)
        mod.provides = "hooks"
        mod.Config = PluginConfig
        mod.apply = lambda ctx, cfg: None  # type: ignore[attr-defined]

        assert mod.name == "mod_plugin"
        assert mod.inject == ("tools",)
        assert mod.provides == "hooks"
        assert mod.Config is PluginConfig
        assert callable(mod.apply)

    def test_class_level_attributes(self) -> None:
        """类作为档口——五样资质以类属性形式呈现。"""

        class ClassPlugin:
            name = "classy"
            inject: tuple[str, ...] = ("memory",)
            provides: str | None = "sandbox"
            Config = PluginConfig

            @staticmethod
            def apply(ctx: Any, config: PluginConfig) -> None:
                pass

        assert ClassPlugin.name == "classy"
        assert ClassPlugin.inject == ("memory",)
        assert ClassPlugin.provides == "sandbox"
        assert ClassPlugin.Config is PluginConfig
        assert callable(ClassPlugin.apply)


# ── SeamRole ────────────────────────────────────────────────


class TestSeamRole:
    """能力三角的角色定义——菜单、厨师、食客，缺一不可。"""

    def test_exactly_three_roles(self) -> None:
        """能力三角恰好三种角色，不多不少。"""
        assert len(SeamRole) == 3

    def test_enum_values(self) -> None:
        """三种角色的值分别是 definition、provider、consumer。"""
        assert SeamRole.DEFINITION.value == "definition"
        assert SeamRole.PROVIDER.value == "provider"
        assert SeamRole.CONSUMER.value == "consumer"

    def test_is_str_enum(self) -> None:
        """SeamRole 继承 str——枚举值可以直接当字符串用。"""
        assert isinstance(SeamRole.DEFINITION, str)
        assert SeamRole.DEFINITION == "definition"
        assert SeamRole.PROVIDER == "provider"
        assert SeamRole.CONSUMER == "consumer"

    def test_all_roles_accessible(self) -> None:
        """三种角色都可以通过枚举名访问。"""
        roles = set(SeamRole)
        assert SeamRole.DEFINITION in roles
        assert SeamRole.PROVIDER in roles
        assert SeamRole.CONSUMER in roles


# ── SeamRegistry ────────────────────────────────────────────


class TestSeamRegistry:
    """能力验证处——管理处的花名册，查验某项能力三角是否齐全。"""

    def test_empty_registry_not_complete(self) -> None:
        """空花名册上什么都查不到——任何能力都不完整。"""
        reg = SeamRegistry()
        assert reg.is_complete("anything") is False

    def test_one_role_incomplete(self) -> None:
        """只有 DEFINITION 不算完整能力——还缺厨师和食客。"""
        reg = SeamRegistry()

        class Def:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        assert reg.is_complete("llm") is False

    def test_two_roles_incomplete(self) -> None:
        """有了菜单和厨师，但没食客——能力依然不完整。"""
        reg = SeamRegistry()

        class Def:
            pass

        class Prov:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        reg.register(Prov, "llm", SeamRole.PROVIDER)
        assert reg.is_complete("llm") is False

    def test_three_roles_complete(self) -> None:
        """三角到齐——菜单、厨师、食客都注册了，能力完整。"""
        reg = SeamRegistry()

        class Def:
            pass

        class Prov:
            pass

        class Cons:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        reg.register(Prov, "llm", SeamRole.PROVIDER)
        reg.register(Cons, "llm", SeamRole.CONSUMER)
        assert reg.is_complete("llm") is True

    def test_multiple_providers(self) -> None:
        """同一道菜可以有多个厨师——只要三角齐全就算完整。"""
        reg = SeamRegistry()

        class Def:
            pass

        class Prov1:
            pass

        class Prov2:
            pass

        class Cons:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        reg.register(Prov1, "llm", SeamRole.PROVIDER)
        reg.register(Prov2, "llm", SeamRole.PROVIDER)
        reg.register(Cons, "llm", SeamRole.CONSUMER)
        assert reg.is_complete("llm") is True
        roles = reg.get_roles("llm")
        assert len(roles[SeamRole.PROVIDER]) == 2

    def test_idempotent_registration(self) -> None:
        """重复登记同一档口——花名册不会重复计数。"""
        reg = SeamRegistry()

        class Def:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        reg.register(Def, "llm", SeamRole.DEFINITION)
        roles = reg.get_roles("llm")
        assert len(roles[SeamRole.DEFINITION]) == 1

    def test_get_seams_empty(self) -> None:
        """空花名册——没有任何已登记的能力门类。"""
        reg = SeamRegistry()
        assert reg.get_seams() == []

    def test_get_seams_returns_registered_names(self) -> None:
        """花名册返回所有已登记的能力门类名称。"""
        reg = SeamRegistry()

        class A:
            pass

        reg.register(A, "llm", SeamRole.DEFINITION)
        reg.register(A, "memory", SeamRole.DEFINITION)
        seams = reg.get_seams()
        assert set(seams) == {"llm", "memory"}

    def test_get_roles_unknown_seam(self) -> None:
        """查一个没登记过的能力——返回空字典。"""
        reg = SeamRegistry()
        assert reg.get_roles("nope") == {}

    def test_get_roles_returns_role_map(self) -> None:
        """查已登记的能力——返回各角色对应的档口列表。"""
        reg = SeamRegistry()

        class Def:
            pass

        class Prov:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        reg.register(Prov, "llm", SeamRole.PROVIDER)
        roles = reg.get_roles("llm")
        assert SeamRole.DEFINITION in roles
        assert SeamRole.PROVIDER in roles
        assert Def in roles[SeamRole.DEFINITION]
        assert Prov in roles[SeamRole.PROVIDER]

    def test_get_missing_roles_unknown_seam(self) -> None:
        """未登记的能力——三种角色全部缺失。"""
        reg = SeamRegistry()
        missing = reg.get_missing_roles("unknown")
        assert set(missing) == {SeamRole.DEFINITION, SeamRole.PROVIDER, SeamRole.CONSUMER}

    def test_get_missing_roles_partial(self) -> None:
        """只登记了菜单——还缺厨师和食客。"""
        reg = SeamRegistry()

        class Def:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        missing = reg.get_missing_roles("llm")
        assert set(missing) == {SeamRole.PROVIDER, SeamRole.CONSUMER}

    def test_get_missing_roles_complete(self) -> None:
        """三角齐全——没有缺失的角色。"""
        reg = SeamRegistry()

        class Def:
            pass

        class Prov:
            pass

        class Cons:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        reg.register(Prov, "llm", SeamRole.PROVIDER)
        reg.register(Cons, "llm", SeamRole.CONSUMER)
        assert reg.get_missing_roles("llm") == []

    def test_consumers_of_empty(self) -> None:
        """没有登记任何食客——食客列表为空。"""
        reg = SeamRegistry()
        assert reg.consumers_of("llm") == []

    def test_consumers_of_registered(self) -> None:
        """登记了两位食客——都能查出来。"""
        reg = SeamRegistry()

        class ConsA:
            pass

        class ConsB:
            pass

        reg.register(ConsA, "llm", SeamRole.CONSUMER)
        reg.register(ConsB, "llm", SeamRole.CONSUMER)
        consumers = reg.consumers_of("llm")
        assert consumers == [ConsA, ConsB]

    def test_is_registered_consumer_exact(self) -> None:
        """登记的食客——可以通过身份验证。"""
        reg = SeamRegistry()

        class Cons:
            pass

        reg.register(Cons, "llm", SeamRole.CONSUMER)
        assert reg.is_registered_consumer("llm", Cons) is True

    def test_is_registered_consumer_subclass(self) -> None:
        """食客的子类也能通过验证——继承身份。"""
        reg = SeamRegistry()

        class Base:
            pass

        class Child(Base):
            pass

        reg.register(Base, "llm", SeamRole.CONSUMER)
        assert reg.is_registered_consumer("llm", Child) is True

    def test_is_registered_consumer_unrelated(self) -> None:
        """没登记的陌生人——通不过身份验证。"""
        reg = SeamRegistry()

        class Cons:
            pass

        class Stranger:
            pass

        reg.register(Cons, "llm", SeamRole.CONSUMER)
        assert reg.is_registered_consumer("llm", Stranger) is False

    def test_is_registered_consumer_unknown_seam(self) -> None:
        """查一个不存在的能力门类的食客——一律不算。"""
        reg = SeamRegistry()

        class Cons:
            pass

        assert reg.is_registered_consumer("nope", Cons) is False


# ── @seam decorator ─────────────────────────────────────────


class TestSeamDecorator:
    """能力标签贴——@seam 装饰器给类贴上「我是什么能力的什么角色」。"""

    def test_attaches_metadata(self) -> None:
        """贴上标签后，__seam_name__ 和 __seam_role__ 属性就出现了。"""

        @seam("shell", SeamRole.DEFINITION)
        class Shell:
            pass

        assert Shell.__seam_name__ == "shell"
        assert Shell.__seam_role__ == SeamRole.DEFINITION

    def test_works_on_protocol(self) -> None:
        """Protocol 也能贴标签——菜单定义接口同样需要登记。"""

        @seam("llm", SeamRole.DEFINITION)
        class LlmDef(Protocol):
            def complete(self, prompt: str) -> str: ...

        assert LlmDef.__seam_name__ == "llm"
        assert LlmDef.__seam_role__ == SeamRole.DEFINITION

    def test_works_on_class(self) -> None:
        """具体实现类也能贴标签——厨师登记在册。"""

        @seam("sandbox", SeamRole.PROVIDER)
        class DockerSandbox:
            pass

        assert DockerSandbox.__seam_name__ == "sandbox"
        assert DockerSandbox.__seam_role__ == SeamRole.PROVIDER

    def test_does_not_register_globally(self) -> None:
        """贴标签只是局部行为——不会自动往全局花名册里登记。"""
        before = get_global_seam_registry().get_seams()

        @seam("isolated", SeamRole.CONSUMER)
        class Isolated:
            pass

        after = get_global_seam_registry().get_seams()
        assert before == after


# ── consume gate ────────────────────────────────────────────


class TestConsumeGate:
    """组合期门——只有登记过的食客才能领取厨师的菜。"""

    def test_registered_consumer_passes(self) -> None:
        """登记过的食客——顺利通过期门，拿到菜。"""
        reg = SeamRegistry()

        class Cons:
            pass

        reg.register(Cons, "llm", SeamRole.CONSUMER)
        provider = object()
        result = consume("llm", provider, Cons, registry=reg)
        assert result is provider

    def test_unregistered_consumer_rejected(self) -> None:
        """没登记的食客——被期门拦住，报 UnauthorizedConsumerError。"""
        reg = SeamRegistry()

        class Authorized:
            pass

        class Intruder:
            pass

        reg.register(Authorized, "llm", SeamRole.CONSUMER)
        with pytest.raises(UnauthorizedConsumerError, match="Intruder"):
            consume("llm", object(), Intruder, registry=reg)

    def test_unarmed_catalog_is_passthrough(self) -> None:
        """如果某道菜没有任何食客登记——期门敞开，人人可取。"""
        reg = SeamRegistry()
        provider = object()
        result = consume("llm", provider, Any, registry=reg)
        assert result is provider

    def test_custom_registry_vs_global(self) -> None:
        """传入自定义花名册就用自己的——不看全局花名册。"""
        custom_reg = SeamRegistry()

        class Cons:
            pass

        custom_reg.register(Cons, "llm", SeamRole.CONSUMER)

        # Global registry has no consumers for "llm" → would be passthrough
        # Custom registry has Cons → should pass
        provider = object()
        result = consume("llm", provider, Cons, registry=custom_reg)
        assert result is provider

    def test_subclass_consumer_passes(self) -> None:
        """食客的子类也能通过期门——继承就是通行证。"""
        reg = SeamRegistry()

        class Base:
            pass

        class Child(Base):
            pass

        reg.register(Base, "llm", SeamRole.CONSUMER)
        provider = object()
        result = consume("llm", provider, Child, registry=reg)
        assert result is provider

    def test_error_message_includes_seam_name(self) -> None:
        """被拦住时，错误消息会告诉你：哪道菜、谁被拦、谁有权。"""
        reg = SeamRegistry()

        class Authorized:
            pass

        class Intruder:
            pass

        reg.register(Authorized, "sandbox", SeamRole.CONSUMER)
        with pytest.raises(UnauthorizedConsumerError) as exc_info:
            consume("sandbox", object(), Intruder, registry=reg)
        assert "sandbox" in str(exc_info.value)
        assert "Intruder" in str(exc_info.value)
        assert "Authorized" in str(exc_info.value)


# ── require_complete ────────────────────────────────────────


class TestRequireComplete:
    """开业前检查——宣布能力「就绪」之前，三角必须齐全。"""

    def test_complete_seam_passes(self) -> None:
        """三角齐全的能力——require_complete 放行，不抛异常。"""
        reg = SeamRegistry()

        class Def:
            pass

        class Prov:
            pass

        class Cons:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)
        reg.register(Prov, "llm", SeamRole.PROVIDER)
        reg.register(Cons, "llm", SeamRole.CONSUMER)

        # Should not raise
        require_complete("llm", registry=reg)

    def test_incomplete_seam_raises(self) -> None:
        """三角缺角——require_complete 抛出 IncompleteSeamError。"""
        reg = SeamRegistry()

        class Def:
            pass

        reg.register(Def, "llm", SeamRole.DEFINITION)

        with pytest.raises(IncompleteSeamError, match="incomplete capability seams"):
            require_complete("llm", registry=reg)

    def test_unknown_seam_raises(self) -> None:
        """查一个从未登记过的能力——一样报错。"""
        reg = SeamRegistry()
        with pytest.raises(IncompleteSeamError):
            require_complete("nonexistent", registry=reg)

    def test_multiple_seam_names_all_complete(self) -> None:
        """同时检查多个能力——全部三角齐全才能通过。"""
        reg = SeamRegistry()

        class Def:
            pass

        class Prov:
            pass

        class Cons:
            pass

        for name in ("llm", "memory"):
            reg.register(Def, name, SeamRole.DEFINITION)
            reg.register(Prov, name, SeamRole.PROVIDER)
            reg.register(Cons, name, SeamRole.CONSUMER)

        require_complete("llm", "memory", registry=reg)

    def test_multiple_seam_names_one_incomplete(self) -> None:
        """多个能力里有一个三角不全——报错并点名谁缺角。"""
        reg = SeamRegistry()

        class Def:
            pass

        class Prov:
            pass

        class Cons:
            pass

        # llm is complete
        reg.register(Def, "llm", SeamRole.DEFINITION)
        reg.register(Prov, "llm", SeamRole.PROVIDER)
        reg.register(Cons, "llm", SeamRole.CONSUMER)

        # memory is incomplete (only definition)
        reg.register(Def, "memory", SeamRole.DEFINITION)

        with pytest.raises(IncompleteSeamError) as exc_info:
            require_complete("llm", "memory", registry=reg)
        assert "memory" in str(exc_info.value)
        # llm should NOT be in the error since it's complete
        error_detail = str(exc_info.value)
        assert "'llm'" not in error_detail or "incomplete" in error_detail

    def test_error_detail_lists_missing_roles(self) -> None:
        """报错消息会列出具体缺了哪些角色——方便排查。"""
        reg = SeamRegistry()

        class Def:
            pass

        reg.register(Def, "tools", SeamRole.DEFINITION)

        with pytest.raises(IncompleteSeamError) as exc_info:
            require_complete("tools", registry=reg)
        msg = str(exc_info.value)
        assert "provider" in msg
        assert "consumer" in msg


# ── SeamKey ─────────────────────────────────────────────────


class TestSeamKey:
    """广场常驻能力目录——枚举出所有已知的能力门类。"""

    EXPECTED_KEYS: frozenset[str] = frozenset(
        {
            "LLM",
            "SANDBOX",
            "MEMORY",
            "STATE_STORE",
            "SEARCH",
            "TOOLS",
            "TRANSPORT",
            "SKILLS",
            "FILE_STORE",
            "OBSERVABILITY",
        }
    )

    def test_all_expected_keys_exist(self) -> None:
        """目录里包含所有预期的能力门类——一个不多一个不少。"""
        actual = frozenset(member.name for member in SeamKey)
        assert actual == self.EXPECTED_KEYS

    def test_required_seam_keys_is_tuple_of_all(self) -> None:
        """REQUIRED_SEAM_KEYS 是 SeamKey 全量的元组形式。"""
        assert isinstance(REQUIRED_SEAM_KEYS, tuple)
        assert set(REQUIRED_SEAM_KEYS) == set(SeamKey)

    def test_seam_key_values(self) -> None:
        """每个能力门类的字符串值都是小写形式。"""
        assert SeamKey.LLM == "llm"
        assert SeamKey.SANDBOX == "sandbox"
        assert SeamKey.MEMORY == "memory"
        assert SeamKey.STATE_STORE == "state_store"
        assert SeamKey.SEARCH == "search"
        assert SeamKey.TOOLS == "tools"
        assert SeamKey.TRANSPORT == "transport"
        assert SeamKey.SKILLS == "skills"
        assert SeamKey.FILE_STORE == "file_store"
        assert SeamKey.OBSERVABILITY == "observability"

    def test_seam_key_is_str_enum(self) -> None:
        """SeamKey 也继承 str——枚举值可直接当字符串用。"""
        assert isinstance(SeamKey.LLM, str)


# ── SeamDeclaration ─────────────────────────────────────────


class TestSeamDeclaration:
    """能力声明数据类——记录「谁声明了什么能力的什么角色」。"""

    def test_fields(self) -> None:
        """声明数据类能正确存储 seam_name、role、cls 三个字段。"""

        class MyDef:
            pass

        decl = SeamDeclaration(seam_name="llm", role=SeamRole.DEFINITION, cls=MyDef)
        assert decl.seam_name == "llm"
        assert decl.role == SeamRole.DEFINITION
        assert decl.cls is MyDef

    def test_frozen(self) -> None:
        """声明是冻结的——创建后不允许修改。"""
        from dataclasses import FrozenInstanceError

        class MyDef:
            pass

        decl = SeamDeclaration(seam_name="x", role=SeamRole.PROVIDER, cls=MyDef)
        with pytest.raises(FrozenInstanceError):
            decl.seam_name = "y"  # type: ignore[misc]


# ── MissingCapabilityError ──────────────────────────────────


class TestMissingCapabilityError:
    """缺失能力异常——找不到某项能力时抛出的错误。"""

    def test_is_key_error(self) -> None:
        """MissingCapabilityError 是 KeyError 的子类——兼容字典查找失败语义。"""
        assert issubclass(MissingCapabilityError, KeyError)

    def test_can_raise_and_catch(self) -> None:
        """可以正常抛出并捕获。"""
        with pytest.raises(MissingCapabilityError):
            raise MissingCapabilityError("llm")
