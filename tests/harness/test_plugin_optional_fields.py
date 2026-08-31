"""Tests for optional typed fields on ``PluginDefinition`` and ``PluginSpec``.

Executable control belongs exclusively to ``PluginSpec.contributes`` and is
compiled into ``CompiledRunPlan.control_entries``. The retired raw ``control``
metadata is intentionally absent from this test surface.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_phase_graph import (
    ContributionRole,
    PhaseContribution,
    SemanticPhase,
)
from lca.harness.plugin_api import (
    PluginContext,
    PluginKind,
    definition_from_plugin,
    plugin,
)


class TestPluginDefinitionDefaults:
    def test_default_declarative_contribution_is_empty_tuple(self) -> None:
        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        @plugin(
            id="test.x",
            layer="L0",
            kind=PluginKind.PRIMITIVE,
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        definition = definition_from_plugin(setup)
        assert definition.spec is not None
        assert definition.spec.contributes == ()
        assert definition.relations == ()
        assert definition.functional_group is None
        assert definition.logic_address is None
        assert definition.contract is None


class TestPluginDecoratorAcceptsTypedKwargs:
    def test_contributes_field(self) -> None:
        """``@plugin`` forwards typed contributions into the native PluginSpec."""

        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        contribution = PhaseContribution(
            phase=SemanticPhase.ACT,
            role=ContributionRole.GOVERN,
            executor="control.act.budget",
            output="act.budget",
            order=50,
            aggregation="deny-on-any-deny",
        )

        @plugin(
            id="test.budget",
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            contributes=(contribution,),
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        definition = definition_from_plugin(setup)
        assert definition.spec is not None
        assert definition.spec.contributes == (contribution,)

    def test_relations_field(self) -> None:
        """``@plugin`` accepts explicit relation declarations."""

        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        relation_entries = ({"target": "test.relation", "kind": "governs"},)

        @plugin(
            id="test.relation",
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            relations=relation_entries,
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        definition = definition_from_plugin(setup)
        assert definition.relations == relation_entries

    def test_functional_group_field(self) -> None:
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

        definition = definition_from_plugin(setup)
        assert definition.functional_group is FunctionalGroup.G6_DECISION

    def test_functional_group_str_input(self) -> None:
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

        definition = definition_from_plugin(setup)
        assert definition.functional_group is FunctionalGroup.G6_DECISION

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
        class Config(BaseModel):
            model_config = {"extra": "forbid"}

        address = LogicAddress(
            functional_group=FunctionalGroup.G6_DECISION,
            control_slot=ControlSlot.THINK_GUARD,
            scope=Scope.TURN,
        )

        @plugin(
            id="test.addr",
            layer="L1",
            kind=PluginKind.PRIMITIVE,
            logic_address=address,
        )
        async def setup(ctx: PluginContext, config: Config) -> None:
            pass

        definition = definition_from_plugin(setup)
        assert definition.logic_address is address

    def test_contract_field(self) -> None:
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

        definition = definition_from_plugin(setup)
        assert definition.contract is contract


class TestTypedContributionsMustBeValid:
    def test_contributions_must_be_list_or_tuple(self) -> None:
        with pytest.raises(TypeError, match="contributes must be list/tuple"):

            class Config(BaseModel):
                model_config = {"extra": "forbid"}

            @plugin(
                id="test.bad_contribution",
                layer="L1",
                kind=PluginKind.PRIMITIVE,
                contributes={"phase": SemanticPhase.THINK},  # type: ignore[arg-type]
            )
            async def setup(ctx: PluginContext, config: Config) -> None:
                pass

    def test_contribution_requires_typed_phase_and_role(self) -> None:
        with pytest.raises(TypeError, match="phase must be SemanticPhase"):

            class Config(BaseModel):
                model_config = {"extra": "forbid"}

            @plugin(
                id="test.bad_contribution_shape",
                layer="L1",
                kind=PluginKind.PRIMITIVE,
                contributes=(
                    {
                        "phase": "think",
                        "role": ContributionRole.GOVERN,
                        "executor": "control.think.guard",
                        "output": "think.guard",
                    },
                ),
            )
            async def setup(ctx: PluginContext, config: Config) -> None:
                pass


class TestRelationsMustBeIterable:
    def test_relations_must_be_list_or_tuple(self) -> None:
        with pytest.raises(TypeError, match="relations must be list/tuple"):

            class Config(BaseModel):
                model_config = {"extra": "forbid"}

            @plugin(
                id="test.bad_relations",
                layer="L1",
                kind=PluginKind.PRIMITIVE,
                relations={"target": "test.target", "kind": "governs"},  # type: ignore[arg-type]
            )
            async def setup(ctx: PluginContext, config: Config) -> None:
                pass

    def test_relation_entries_must_be_mappings(self) -> None:
        with pytest.raises(TypeError, match=r"relations\[0\] must be mapping"):

            class Config(BaseModel):
                model_config = {"extra": "forbid"}

            @plugin(
                id="test.bad_relation_entry",
                layer="L1",
                kind=PluginKind.PRIMITIVE,
                relations=("governs",),  # type: ignore[arg-type]
            )
            async def setup(ctx: PluginContext, config: Config) -> None:
                pass


class TestDeclarativeControlProjection:
    def test_default_profile_projects_every_executable_control_from_native_specs(self) -> None:
        from lca.harness.profile.plan_compiler import compile_plan
        from lca.harness.profile.resolve import resolve_profile

        plan = compile_plan(resolve_profile("profiles/web-standard.yaml"))
        entries = plan.control_entries

        assert len(entries) == 12
        assert {entry.executor_capability for entry in entries} == {
            "control.perceive.context",
            "control.think.guard",
            "control.act.authorize",
            "control.act.budget",
            "control.act.constrain",
            "control.act.execute",
            "control.act.safe-boundary",
            "control.remember.admit",
            "control.stop.decide",
            "control.stop.focus",
            "control.observe.checkpoint",
            "control.observe.wildcard",
        }
        assert all(entry.predicate == "true" for entry in entries)
        assert all(entry.evidence_required for entry in entries)
