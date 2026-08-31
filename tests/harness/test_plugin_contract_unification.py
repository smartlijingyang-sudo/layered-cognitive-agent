"""Tests for ADR-0110 PR-A: 3-key → canonical PluginContract unification.

The 6-dim ``LogicAddress`` flat struct and the bare ``functional_group=``
shorthand must both be foldable into the canonical 9-section
``PluginContract``. ``contract=`` wins over both.
"""

from __future__ import annotations

from pydantic import BaseModel

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
    compose_plugin_contract,
    contract_snapshot_for_meta,
    logic_address_to_plugin_contract,
)
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.harness.plugin.plugin_api import plugin
from lca.harness.plugin.plugin_manifest import PluginDefinition, PluginKind


class _Cfg(BaseModel):
    pass


# ── logic_address_to_plugin_contract (D2 helper) ──────────────────


class TestLogicAddressToPluginContract:
    def test_full_logic_address_maps_to_5_sections(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G7_EXECUTION,
            control_slot=ControlSlot.OBSERVE_WILDCARD,
            scope=Scope.RUN,
            authority=("plugin.serve",),
            evidence=("phase_act.checked", "phase_act.served"),
            revision="v1",
        )
        c = logic_address_to_plugin_contract(addr)

        assert c.identity == PluginIdentity(version="v1")
        assert c.architecture.group is FunctionalGroup.G7_EXECUTION
        assert c.architecture.control_slots == (ControlSlot.OBSERVE_WILDCARD,)
        assert c.lifecycle.allowed_scopes == (Scope.RUN,)
        assert c.authority.grants == ("plugin.serve",)
        assert c.observability.descriptors == ("phase_act.checked", "phase_act.served")

    def test_partial_logic_address_keeps_missing_dims_empty(self) -> None:
        addr = LogicAddress(functional_group=FunctionalGroup.G5_COGNITION)
        c = logic_address_to_plugin_contract(addr)

        assert c.architecture.group is FunctionalGroup.G5_COGNITION
        assert c.architecture.control_slots == ()
        assert c.lifecycle.allowed_scopes == ()
        assert c.authority.grants == ()
        assert c.observability.descriptors == ()
        assert c.identity.version == ""

    def test_revision_none_normalizes_to_empty_string(self) -> None:
        addr = LogicAddress(functional_group=FunctionalGroup.G1_IDENTITY, revision=None)
        c = logic_address_to_plugin_contract(addr)
        assert c.identity.version == ""

    def test_empty_authority_and_evidence_carry_over(self) -> None:
        addr = LogicAddress(
            functional_group=FunctionalGroup.G3_FACTS,
            authority=(),
            evidence=(),
        )
        c = logic_address_to_plugin_contract(addr)
        assert c.authority.grants == ()
        assert c.observability.descriptors == ()


# ── compose_plugin_contract: priority resolution ────────────────────


class TestComposePriority:
    def test_contract_wins_over_logic_address(self) -> None:
        winner = PluginContract(
            architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION)
        )
        loser = LogicAddress(functional_group=FunctionalGroup.G5_COGNITION)

        assert compose_plugin_contract(logic_address=loser, contract=winner) is winner

    def test_contract_wins_over_functional_group_string(self) -> None:
        winner = PluginContract(
            architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION)
        )
        assert compose_plugin_contract(functional_group="G5", contract=winner) is winner

    def test_logic_address_wins_over_functional_group_when_no_contract(self) -> None:
        addr = LogicAddress(functional_group=FunctionalGroup.G7_EXECUTION)
        c = compose_plugin_contract(
            functional_group=FunctionalGroup.G3_FACTS,
            logic_address=addr,
        )
        assert c.architecture.group is FunctionalGroup.G7_EXECUTION

    def test_functional_group_string_only(self) -> None:
        c = compose_plugin_contract(functional_group="G6")
        assert c.architecture.group is FunctionalGroup.G6_DECISION
        assert c.architecture.control_slots == ()
        assert c.lifecycle.allowed_scopes == ()

    def test_functional_group_enum_only(self) -> None:
        c = compose_plugin_contract(functional_group=FunctionalGroup.G5_COGNITION)
        assert c.architecture.group is FunctionalGroup.G5_COGNITION

    def test_all_none_yields_empty_contract(self) -> None:
        c = compose_plugin_contract()
        assert c.architecture.group is None
        assert c.architecture.control_slots == ()
        assert c.architecture.role == ""
        assert c.lifecycle.allowed_scopes == ()
        assert c.authority.grants == ()
        assert c.observability.descriptors == ()
        assert c.identity.version == ""


# ── contract_snapshot_for_meta (canonical meta projection) ─────────


class TestContractSnapshot:
    def test_full_contract_round_trips_through_snapshot(self) -> None:
        c = PluginContract(
            identity=PluginIdentity(id="demo.x", version="2.0", owner="lca"),
            architecture=ArchitectureContract(
                group=FunctionalGroup.G7_EXECUTION,
                role="standard_act",
                control_slots=(ControlSlot.OBSERVE_WILDCARD,),
            ),
            lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
            authority=AuthorityContract(
                grants=("plugin.serve",),
                risk_level="low",
                requires_approval=False,
            ),
            observability=EvidenceContract(
                descriptors=("phase_act.checked",),
                privacy_class="internal",
                replay_safe=True,
            ),
        )
        snap = contract_snapshot_for_meta(c)
        assert snap["identity"]["id"] == "demo.x"
        assert snap["identity"]["version"] == "2.0"
        assert snap["identity"]["owner"] == "lca"
        assert snap["architecture"]["group"] == "G7"
        assert snap["architecture"]["role"] == "standard_act"
        assert snap["architecture"]["control_slots"] == ["observe.*"]
        assert snap["lifecycle"]["allowed_scopes"] == ["run"]
        assert snap["authority"]["grants"] == ["plugin.serve"]
        assert snap["authority"]["risk_level"] == "low"
        assert snap["authority"]["requires_approval"] is False
        assert snap["observability"]["descriptors"] == ["phase_act.checked"]
        assert snap["observability"]["privacy_class"] == "internal"
        assert snap["observability"]["replay_safe"] is True

    def test_empty_contract_yields_default_snapshot(self) -> None:
        snap = contract_snapshot_for_meta(PluginContract())
        assert snap == {
            "identity": {"id": "", "version": "", "owner": ""},
            "architecture": {"group": None, "role": "", "control_slots": []},
            "capabilities": {"provides": [], "requires": [], "effect_classes": []},
            "lifecycle": {
                "allowed_scopes": [],
                "lease_seconds": None,
                "dispose_strategy": "",
            },
            "authority": {"grants": [], "risk_level": "", "requires_approval": False},
            "observability": {
                "descriptors": [],
                "privacy_class": "",
                "replay_safe": True,
            },
            "verification": {
                "schemas": [],
                "fixtures": [],
                "property_tests": [],
                "test_suite": "",
            },
        }


# ── @plugin() decorator: end-to-end alias folding ──────────────────


class TestPluginDecoratorAliases:
    def _resolve(self, fn) -> PluginDefinition:
        return fn._lca_definition  # type: ignore[attr-defined]

    def test_contract_key_wins_over_logic_address(self) -> None:
        @plugin(
            id="unif.contract",
            Config=_Cfg,
            provides=("unif.contract",),
            layer="L2",
            kind=PluginKind.PRIMITIVE,
            functional_group=FunctionalGroup.G3_FACTS,
            logic_address=LogicAddress(functional_group=FunctionalGroup.G5_COGNITION),
            contract=PluginContract(
                architecture=ArchitectureContract(group=FunctionalGroup.G10_COMPOSITION)
            ),
        )
        async def setup(ctx, config): ...

        d = self._resolve(setup)
        assert d.contract is not None
        assert d.contract.architecture.group is FunctionalGroup.G10_COMPOSITION

    def test_logic_address_only_folds_into_contract(self) -> None:
        @plugin(
            id="unif.logic_addr",
            Config=_Cfg,
            provides=("unif.logic_addr",),
            layer="L2",
            kind=PluginKind.PRIMITIVE,
            logic_address=LogicAddress(
                functional_group=FunctionalGroup.G7_EXECUTION,
                control_slot=ControlSlot.OBSERVE_WILDCARD,
                scope=Scope.RUN,
                authority=("plugin.serve",),
                evidence=("phase_x.checked",),
                revision="v3",
            ),
        )
        async def setup(ctx, config): ...

        d = self._resolve(setup)
        assert d.contract is not None
        assert d.contract.architecture.group is FunctionalGroup.G7_EXECUTION
        assert d.contract.architecture.control_slots == (ControlSlot.OBSERVE_WILDCARD,)
        assert d.contract.lifecycle.allowed_scopes == (Scope.RUN,)
        assert d.contract.authority.grants == ("plugin.serve",)
        assert d.contract.observability.descriptors == ("phase_x.checked",)
        assert d.contract.identity.version == "v3"

    def test_functional_group_only_minimal_contract(self) -> None:
        @plugin(
            id="unif.fg",
            Config=_Cfg,
            provides=("unif.fg",),
            layer="L2",
            kind=PluginKind.PRIMITIVE,
            functional_group=FunctionalGroup.G6_DECISION,
        )
        async def setup(ctx, config): ...

        d = self._resolve(setup)
        assert d.contract is not None
        assert d.contract.architecture.group is FunctionalGroup.G6_DECISION
        assert d.contract.architecture.control_slots == ()
        assert d.contract.identity.version == ""

    def test_contract_snapshot_in_meta(self) -> None:
        @plugin(
            id="unif.meta",
            Config=_Cfg,
            provides=("unif.meta",),
            layer="L2",
            kind=PluginKind.PRIMITIVE,
            contract=PluginContract(
                architecture=ArchitectureContract(group=FunctionalGroup.G5_COGNITION)
            ),
        )
        async def setup(ctx, config): ...

        meta = setup.meta  # type: ignore[attr-defined]
        assert "contract_snapshot" in meta, "canonical snapshot must be in cordis meta"
        snap = meta["contract_snapshot"]
        assert snap["architecture"]["group"] == "G5"

    def test_legacy_keys_still_propagate_to_definition_for_backcompat(self) -> None:
        """Pre-ADR-0110 readers (``definition.logic_address`` / ``definition.functional_group``)
        must keep working during the deprecation window; D3 schedules their
        removal in PR-D, six months out.
        """

        @plugin(
            id="unif.backcompat",
            Config=_Cfg,
            provides=("unif.backcompat",),
            layer="L2",
            kind=PluginKind.PRIMITIVE,
            functional_group=FunctionalGroup.G4_PERCEPTION,
            logic_address=LogicAddress(functional_group=FunctionalGroup.G5_COGNITION),
        )
        async def setup(ctx, config): ...

        d = self._resolve(setup)
        assert d.functional_group is FunctionalGroup.G4_PERCEPTION
        assert d.logic_address is not None
        assert d.logic_address.functional_group is FunctionalGroup.G5_COGNITION
