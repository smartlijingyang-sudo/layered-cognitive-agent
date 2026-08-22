"""Tests for PluginDefinition 4 个 PR-2 新增可选字段（ADR-0074 PR-2）。

覆盖：

- PluginDefinition 默认值（control=(), functional_group=None, logic_address=None, contract=None）
- @plugin 装饰器接受 control / functional_group / logic_address / contract kwargs
- definition_from_plugin 提取所有字段（包括 meta fallback for functional_group）
- 缺字段 = 不破旧 plugin
- 迁移的 core plugins（repeat_tool_call / tool_loop_breaker / stop_rule）正确产出 ControlEntry
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.plugin_contract import (
    ArchitectureContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.logic_address import LogicAddress
from lca.harness.plugin_api import (
    PluginContext,
    PluginKind,
    definition_from_plugin,
    plugin,
)


class TestPluginDefinitionDefaults:
    def test_default_control_is_empty_tuple(self) -> None:
        """opt-in: 未声明 control = ()。"""

        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        @plugin(
            id="test.x",
            layer="L0",
            kind=PluginKind.PRIMITIVE,
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        from lca.harness.plugin_api import definition_from_plugin

        defn = definition_from_plugin(setup)
        assert defn.control == ()
        assert defn.functional_group is None
        assert defn.logic_address is None
        assert defn.contract is None


class TestPluginDecoratorAcceptsPR2Kwargs:
    def test_control_field(self) -> None:
        """@plugin 接受 control= tuple[dict]。"""

        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        control_entry = (
            {
                "slot": ControlSlot.ACT_BUDGET.value,
                "order": 50,
                "aggregation": "deny_on_exhausted",
                "failure_mode": "deny",
            },
        )

        @plugin(
            id="test.budget",
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            control=control_entry,
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        defn = definition_from_plugin(setup)
        assert defn.control == control_entry

    def test_functional_group_field(self) -> None:
        """@plugin 接受 functional_group= enum / str。"""

        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        @plugin(
            id="test.g6",
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            functional_group=FunctionalGroup.G6_DECISION,
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        defn = definition_from_plugin(setup)
        assert defn.functional_group is FunctionalGroup.G6_DECISION

    def test_functional_group_str_input(self) -> None:
        """@plugin functional_group 也接受 str 并归一化。"""

        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        @plugin(
            id="test.g6.str",
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            functional_group="G6",
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        defn = definition_from_plugin(setup)
        assert defn.functional_group is FunctionalGroup.G6_DECISION

    def test_functional_group_invalid_str_raises(self) -> None:
        with pytest.raises(ValueError, match="functional_group"):

            class Config(BaseModel):
                model_config = {"extra": "forbid"}

            @plugin(
                id="test.bad",
                layer="L1",
                kind=PluginKind.PRIMITIVE,
                functional_group="G99",
            )
            async def setup(ctx: PluginContext, config: Config) -> None:
                pass

    def test_logic_address_field(self) -> None:
        """@plugin 接受 logic_address= LogicAddress。"""

        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        addr = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
            scope=Scope.TURN,
        )

        @plugin(
            id="test.addr",
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            logic_address=addr,
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        defn = definition_from_plugin(setup)
        assert defn.logic_address is addr

    def test_contract_field(self) -> None:
        """@plugin 接受 contract= PluginContract。"""

        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        contract = PluginContract(
            identity=PluginIdentity(id="test.contract", version="v1"),
            architecture=ArchitectureContract(group=FunctionalGroup.G6_DECISION),
        )

        @plugin(
            id="test.contract",
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            contract=contract,
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        defn = definition_from_plugin(setup)
        assert defn.contract is contract


class TestControlMustBeIterable:
    """@plugin control= 必须是 list/tuple；其他类型 → TypeError。"""

    def test_control_must_be_list_or_tuple(self) -> None:
        with pytest.raises(TypeError, match="control must be list/tuple"):

            class Config(BaseModel):
                model_config = {"extra": "forbid"}

            @plugin(
                id="test.bad_ctrl",
                layer="L1",
                kind=PluginKind.PRIMITIVE,
                control={"slot": "think.guard"},  # dict = not allowed
            )
            async def setup(ctx: PluginContext, config: Config) -> None:
                pass


class TestMigratedCorePlugins:
    """repeat_tool_call / tool_loop_breaker / stop_rule 已迁移到 PR-2 typed 字段。

    验证：

    - 三个插件都正确产出 functional_group + logic_address
    - ControlPlan 解析出 3 个 entry：2 个 think.guard + 1 个 stop.decide
    - 每条 entry 都携带 reads / emits / order / aggregation / failure_mode
    """

    def test_repeat_tool_call_has_typed_contract(self) -> None:
        from lca.plugins.gates.repeat_tool_call import setup as rtc_setup

        defn = definition_from_plugin(rtc_setup)
        assert defn.functional_group is FunctionalGroup.G6_DECISION
        assert defn.logic_address is not None
        assert defn.logic_address.control_slot is ControlSlot.THINK_GUARD
        assert defn.logic_address.scope is Scope.TURN
        assert len(defn.control) == 1
        entry = defn.control[0]
        assert entry["slot"] == "think.guard"
        assert entry["order"] == 10
        assert entry["aggregation"] == "decision_priority"
        assert entry["failure_mode"] == "deny"

    def test_tool_loop_breaker_has_typed_contract(self) -> None:
        from lca.plugins.gates.tool_loop_breaker import setup as tlb_setup

        defn = definition_from_plugin(tlb_setup)
        assert defn.functional_group is FunctionalGroup.G6_DECISION
        assert defn.logic_address is not None
        assert defn.logic_address.control_slot is ControlSlot.THINK_GUARD
        assert len(defn.control) == 1
        entry = defn.control[0]
        assert entry["slot"] == "think.guard"
        assert entry["order"] == 20

    def test_stop_rule_has_typed_contract(self) -> None:
        from lca.plugins.runtime.stop_rule import setup as sr_setup

        defn = definition_from_plugin(sr_setup)
        assert defn.functional_group is FunctionalGroup.G6_DECISION
        assert defn.logic_address is not None
        assert defn.logic_address.control_slot is ControlSlot.STOP_DECIDE
        assert defn.logic_address.scope is Scope.RUN
        assert len(defn.control) == 1
        entry = defn.control[0]
        assert entry["slot"] == "stop.decide"
        assert entry["aggregation"] == "stop_on_any_stop"
        assert entry["failure_mode"] == "stop"


class TestResolverPicksTypedControl:
    """project_control_plan 应该读 PluginDefinition.control typed field。"""

    def test_resolver_uses_typed_control(self) -> None:
        from lca.harness.profile.control_plan_resolver import project_control_plan
        from lca.harness.profile.resolve import resolve_profile

        resolved = resolve_profile("profiles/web-standard.yaml")
        plan = project_control_plan(resolved)

        # Every production slot is contributed by a concrete loaded plugin.
        assert len(plan.entries) == 12

        plugins_in_order = [entry.plugin_id for entry in plan.entries]
        assert "gate.repeat-tool-call" in plugins_in_order
        assert "gate.tool-loop-breaker" in plugins_in_order
        assert "stop_rule.default" in plugins_in_order
        assert "body.simple.act-budget" in plugins_in_order
        assert not any(plugin_id.startswith("control.default.") for plugin_id in plugins_in_order)

        # by_slot index
        from lca.contracts.protocols.control_plan import slot_entries

        think_guard_entries = slot_entries(plan, ControlSlot.THINK_GUARD)
        assert [e.plugin_id for e in think_guard_entries] == [
            "gate.repeat-tool-call",
            "gate.tool-loop-breaker",
        ]
        stop_decide_entries = slot_entries(plan, ControlSlot.STOP_DECIDE)
        assert [e.plugin_id for e in stop_decide_entries] == ["stop_rule.default"]
