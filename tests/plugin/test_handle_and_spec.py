"""档口运营日志与入驻申请表测试 —— PluginHandle、PluginSpec、DisposableList、EffectMeta、PluginState。

这些数据结构是美食广场的日常运营工具：
- 入驻申请表（PluginSpec）：档口入驻时填写的表单，声明名字、需要的设备、提供的服务
- 营业状态机（PluginState）：档口从等待→装修→营业→卸货→关门的全生命周期
- 档口运营日志（PluginHandle）：记录档口当前状态、关灯清单、提供的服务
- 关灯清单（DisposableList）：走的时候逆序执行清理
- 效果诊断节点（EffectMeta）：关灯清单的树状诊断信息
- 中断判定（is_bailed）：判断广播监听者是否要求中断
"""

from __future__ import annotations

import pytest

from lca.layer0_infra.plugin.kernel import PluginHandle, PluginSpec, PluginState
from lca.layer0_infra.plugin.kernel._disposable import DisposableList
from lca.layer0_infra.plugin.kernel._effect_meta import EffectMeta
from lca.layer0_infra.plugin.kernel._types import is_bailed


class TestPluginState:
    """营业状态机测试 —— 档口从等待到关门的全部状态。

    PENDING(等待入驻) → LOADING(装修中) → ACTIVE(营业中)
    → UNLOADING(卸货中) → DISPOSED(已关门)，另有 FAILED(出故障了)
    """

    def test_all_states_exist(self):
        """所有营业阶段都已定义——管理处不会漏掉任何一个阶段。"""
        assert PluginState.PENDING
        assert PluginState.LOADING
        assert PluginState.ACTIVE
        assert PluginState.FAILED
        assert PluginState.UNLOADING
        assert PluginState.DISPOSED

    def test_string_values(self):
        """每个状态的值都是小写英文字符串——方便日志和序列化。"""
        assert PluginState.PENDING.value == "pending"
        assert PluginState.LOADING.value == "loading"
        assert PluginState.ACTIVE.value == "active"
        assert PluginState.FAILED.value == "failed"
        assert PluginState.UNLOADING.value == "unloading"
        assert PluginState.DISPOSED.value == "disposed"

    def test_is_str_enum(self):
        """状态枚举继承自 str——可以直接当字符串比较。"""
        assert isinstance(PluginState.PENDING, str)
        assert PluginState.ACTIVE == "active"


class TestPluginSpec:
    """入驻申请表测试 —— 档口入驻时填写的表单（不可变数据类）。"""

    def test_frozen_dataclass(self):
        """申请表一旦提交就不可修改——管理处不接受涂改。"""
        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None)
        with pytest.raises(AttributeError):
            spec.name = "changed"

    def test_defaults(self):
        """申请表只填必填项时，可选字段都有合理的默认值。"""
        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None)
        assert spec.inject == ()
        assert spec.provides is None
        assert spec.validate is None
        assert spec.is_class is False

    def test_custom_values(self):
        """申请表所有字段都能自定义——名字、依赖、提供的服务、校验函数、是否类插件。"""

        def apply_fn(ctx, cfg):
            return None

        spec = PluginSpec(
            name="custom",
            apply=apply_fn,
            inject=("dep1", "dep2"),
            provides="svc",
            validate=lambda cfg: cfg,
            is_class=True,
        )
        assert spec.name == "custom"
        assert spec.apply is apply_fn
        assert spec.inject == ("dep1", "dep2")
        assert spec.provides == "svc"
        assert spec.validate is not None
        assert spec.is_class is True


class TestPluginHandle:
    """档口运营日志测试 —— 记录档口状态、关灯清单、提供的服务。"""

    def test_dependencies_property(self):
        """dependencies 属性就是入驻申请表上的「需要设备」列表。"""
        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None)
        handle = PluginHandle(
            entry_id="test",
            spec=spec,
            config={},
            injected=("dep1", "dep2"),
        )
        assert handle.dependencies == ("dep1", "dep2")
        assert handle.dependencies is handle.injected

    def test_get_effects_meta(self):
        """关灯清单附带诊断标签——方便排查哪盏灯是谁登记的。"""
        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None)
        handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())

        meta1 = EffectMeta(label="effect1")
        meta2 = EffectMeta(label="effect2")
        handle.effects.append((lambda: None, meta1))
        handle.effects.append((lambda: None, meta2))

        result = handle.get_effects_meta()
        assert len(result) == 2
        assert result[0].label == "effect1"
        assert result[1].label == "effect2"

    def test_get_effects_meta_skips_none(self):
        """关灯清单里没有标签的项目会被跳过——只返回有诊断信息的。"""
        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None)
        handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())

        handle.effects.append((lambda: None, EffectMeta(label="has_meta")))
        handle.effects.append((lambda: None, None))

        result = handle.get_effects_meta()
        assert len(result) == 1
        assert result[0].label == "has_meta"

    def test_default_state_is_pending(self):
        """新档口的初始状态是「等待入驻」——还没开始装修。"""
        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None)
        handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())
        assert handle.state is PluginState.PENDING

    @pytest.mark.asyncio
    async def test_await_settled_no_inertia(self):
        """没有未完成任务且没有错误时，await_settled 直接返回自己。"""
        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None)
        handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())
        result = await handle.await_settled()
        assert result is handle

    @pytest.mark.asyncio
    async def test_await_settled_with_error(self):
        """如果档口运营过程中出了错，await_settled 会把错误抛出来。"""
        spec = PluginSpec(name="test", apply=lambda ctx, cfg: None)
        handle = PluginHandle(entry_id="test", spec=spec, config={}, injected=())
        handle.error = ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await handle.await_settled()


class TestDisposableList:
    """关灯清单测试 —— 走的时候逆序执行清理。

    想象一个Stack便签：最后贴上去的在最上面，撕的时候也从最上面开始。
    """

    def test_push_returns_remover(self):
        """push 返回一个移除函数——调用后该项目从清单上消失。"""
        dl = DisposableList()
        remover = dl.push("value")
        assert callable(remover)
        assert len(dl) == 1

        # Remover removes the value
        assert remover() is True
        assert len(dl) == 0

        # Second call returns False (already removed)
        assert remover() is False

    def test_delete_by_value(self):
        """delete 按值精确删除——O(1) 快速定位。"""
        dl = DisposableList()
        val1 = "first"
        val2 = "second"
        dl.push(val1)
        dl.push(val2)

        assert len(dl) == 2
        assert dl.delete(val1) is True
        assert len(dl) == 1

        # val1 already deleted
        assert dl.delete(val1) is False

    def test_clear_returns_lifo(self):
        """关灯清单：逆序返回所有待清理项，然后清空——后进先出。"""
        dl = DisposableList()
        dl.push("first")
        dl.push("second")
        dl.push("third")

        result = dl.clear()
        assert result == ["third", "second", "first"]
        assert len(dl) == 0

    def test_len(self):
        """len 返回清单上当前的待清理项数量。"""
        dl = DisposableList()
        assert len(dl) == 0
        dl.push("a")
        assert len(dl) == 1
        dl.push("b")
        assert len(dl) == 2
        dl.delete("a")
        assert len(dl) == 1

    def test_iter(self):
        """遍历关灯清单时按插入顺序——先贴的在前。"""
        dl = DisposableList()
        dl.push("first")
        dl.push("second")
        dl.push("third")

        result = list(dl)
        assert result == ["first", "second", "third"]


class TestEffectMeta:
    """效果诊断节点测试 —— 关灯清单的树状诊断信息。

    每个 effect 可以附带一个 EffectMeta 节点，形成一棵诊断树，
    方便排查「这盏灯是谁登记的、属于哪个效果」。
    """

    def test_label_stored(self):
        """诊断节点的标签原样保存——用于在排查时快速识别。"""
        meta = EffectMeta(label="test_label")
        assert meta.label == "test_label"

    def test_children_default_empty(self):
        """新建的诊断节点默认没有子节点——光杆一个。"""
        meta = EffectMeta(label="test")
        assert meta.children == []

    def test_children_mutable(self):
        """子节点列表可以动态追加——构建诊断树。"""
        parent = EffectMeta(label="parent")
        child1 = EffectMeta(label="child1")
        child2 = EffectMeta(label="child2")

        parent.children.append(child1)
        parent.children.append(child2)

        assert len(parent.children) == 2
        assert parent.children[0].label == "child1"
        assert parent.children[1].label == "child2"


class TestIsBailed:
    """中断判定测试 —— 判断广播监听者是否要求中断传播。

    在广场广播系统中，如果某个档口听到广播后返回了有意义的值
    （非 None、非 False），就认为它要求中断：「够了，不用再往下传了」。
    """

    def test_non_none_non_false_is_true(self):
        """非 None 且非 False 的值都算「需要中断」——包括 0、空串、空列表。"""
        assert is_bailed(True) is True
        assert is_bailed(0) is True
        assert is_bailed("") is True
        assert is_bailed([]) is True
        assert is_bailed({}) is True
        assert is_bailed("text") is True
        assert is_bailed(42) is True

    def test_none_is_false(self):
        """None 不算中断——「我听到了，但没什么要补充的」。"""
        assert is_bailed(None) is False

    def test_false_is_false(self):
        """False 也不算中断——「我听到了，但不需要停」。"""
        assert is_bailed(False) is False

    def test_truthy_values(self):
        """各种 truthy 值都算中断——有东西要传达。"""
        assert is_bailed(1) is True
        assert is_bailed([1, 2, 3]) is True
        assert is_bailed({"key": "value"}) is True
        assert is_bailed(object()) is True
