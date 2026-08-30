"""Tests for PluginContract 9 段契约（ADR-0069 §六 + tracker §12）。"""

from __future__ import annotations

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    CapabilityContract,
    EvidenceContract,
    LifecycleContract,
    OwnershipContract,
    PluginContract,
    PluginIdentity,
    VerificationContract,
    is_plugin_contract_empty,
    plugin_contract_control_slots,
    plugin_contract_functional_group,
)


class TestPluginIdentity:
    def test_default_empty(self) -> None:
        ident = PluginIdentity()
        assert ident.id == ""
        assert ident.version == ""
        assert ident.owner == ""

    def test_with_values(self) -> None:
        ident = PluginIdentity(id="plugin.x", version="1.0.0", owner="team-a")
        assert ident.id == "plugin.x"
        assert ident.version == "1.0.0"
        assert ident.owner == "team-a"


class TestArchitectureContract:
    def test_default_empty(self) -> None:
        arch = ArchitectureContract()
        assert arch.group is None
        assert arch.role == ""
        assert arch.control_slots == ()

    def test_with_values(self) -> None:
        arch = ArchitectureContract(
            group=FunctionalGroup.G6_DECISION,
            role="policy_filter",
            control_slots=(ControlSlot.THINK_GUARD,),
        )
        assert arch.group is FunctionalGroup.G6_DECISION
        assert arch.role == "policy_filter"
        assert arch.control_slots == (ControlSlot.THINK_GUARD,)

    def test_str_inputs_normalized(self) -> None:
        arch = ArchitectureContract(
            group="G6",
            control_slots=("think.guard", "act.budget"),
        )
        assert arch.group is FunctionalGroup.G6_DECISION
        assert arch.control_slots == (ControlSlot.THINK_GUARD, ControlSlot.ACT_BUDGET)


class TestCapabilityContract:
    def test_default(self) -> None:
        cap = CapabilityContract()
        assert cap.provides == ()
        assert cap.requires == ()
        assert cap.effect_classes == ()


class TestOwnershipContract:
    def test_default_state_authority_false(self) -> None:
        """Reducer 是唯一状态写入者；plugin 默认无 state_authority。"""
        own = OwnershipContract()
        assert own.state_authority is False

    def test_with_state_authority(self) -> None:
        own = OwnershipContract(state_authority=True, reads=("state.x",))
        assert own.state_authority is True


class TestAuthorityContract:
    def test_default_no_approval(self) -> None:
        auth = AuthorityContract()
        assert auth.requires_approval is False
        assert auth.risk_level == ""

    def test_high_risk_requires_approval(self) -> None:
        auth = AuthorityContract(risk_level="high", requires_approval=True, grants=("cap.budget",))
        assert auth.risk_level == "high"
        assert auth.requires_approval is True


class TestLifecycleContract:
    def test_default(self) -> None:
        lc = LifecycleContract()
        assert lc.allowed_scopes == ()
        assert lc.lease_seconds is None
        assert lc.dispose_strategy == ""

    def test_with_scopes(self) -> None:
        lc = LifecycleContract(
            allowed_scopes=(Scope.RUN, Scope.TURN),
            lease_seconds=3600,
            dispose_strategy="graceful",
        )
        assert lc.allowed_scopes == (Scope.RUN, Scope.TURN)
        assert lc.lease_seconds == 3600

    def test_str_scopes_normalized(self) -> None:
        lc = LifecycleContract(allowed_scopes=("run", "turn"))
        assert lc.allowed_scopes == (Scope.RUN, Scope.TURN)


class TestEvidenceContract:
    def test_default_replay_safe(self) -> None:
        ev = EvidenceContract()
        assert ev.replay_safe is True
        assert ev.privacy_class == ""

    def test_sensitive_evidence(self) -> None:
        ev = EvidenceContract(
            descriptors=("policy.x",),
            privacy_class="sensitive",
            replay_safe=False,
        )
        assert ev.descriptors == ("policy.x",)
        assert ev.privacy_class == "sensitive"
        assert ev.replay_safe is False


class TestVerificationContract:
    def test_default(self) -> None:
        v = VerificationContract()
        assert v.test_suite == ""
        assert v.schemas == ()


class TestPluginContractRoot:
    def test_empty_contract(self) -> None:
        contract = PluginContract()
        assert is_plugin_contract_empty(contract)

    def test_filled_contract_not_empty(self) -> None:
        contract = PluginContract(identity=PluginIdentity(id="x"))
        assert not is_plugin_contract_empty(contract)

    def test_control_slots_helper(self) -> None:
        contract = PluginContract(
            architecture=ArchitectureContract(control_slots=(ControlSlot.ACT_AUTHORIZE,))
        )
        assert plugin_contract_control_slots(contract) == (ControlSlot.ACT_AUTHORIZE,)

    def test_functional_group_helper(self) -> None:
        contract = PluginContract(
            architecture=ArchitectureContract(group=FunctionalGroup.G6_DECISION)
        )
        assert plugin_contract_functional_group(contract) is FunctionalGroup.G6_DECISION

    def test_contribution_tuple_enforced(self) -> None:
        contract = PluginContract(contribution=[{"slot": "think.guard"}])
        assert contract.contribution == ({"slot": "think.guard"},)


class TestPluginContractIsEmpty:
    """Default 9 段都为空 = is_empty=True（author 未声明）。"""

    def test_all_defaults_empty(self) -> None:
        contract = PluginContract()
        assert is_plugin_contract_empty(contract)

    def test_single_field_filled_not_empty(self) -> None:
        cases = [
            PluginContract(identity=PluginIdentity(id="x")),
            PluginContract(architecture=ArchitectureContract(group=FunctionalGroup.G1_IDENTITY)),
            PluginContract(capabilities=CapabilityContract(provides=("cap.x",))),
            PluginContract(ownership=OwnershipContract(state_authority=True)),
            PluginContract(authority=AuthorityContract(risk_level="low")),
            PluginContract(lifecycle=LifecycleContract(lease_seconds=60)),
            PluginContract(observability=EvidenceContract(replay_safe=False)),
            PluginContract(verification=VerificationContract(test_suite="x")),
            PluginContract(contribution=({"slot": "x"},)),
        ]
        for c in cases:
            assert not is_plugin_contract_empty(c), f"expected not empty: {c}"
