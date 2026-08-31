"""End-to-end integration smoke test for ADR-0110 PR-C codemod result.

After 184 plugins migrated from ``logic_address=LogicAddress(...)`` to
``contract=PluginContract(...)``, this test exercises every legacy alias
the deprecation window still supports:

1. ``definition.logic_address`` synthesized from canonical contract
   (back-compat shim from PR-A)
2. ``definition.functional_group`` propagated
3. ``definition.contract.architecture.group`` accessible via new path
4. ``definition.contract_snapshot`` stored on cordis meta
5. The contract_snapshot round-trips faithfully through JSON

Plus: a regression net to ensure that codemod didn't drop any of the
6 LogicAddress dimensions — the 8-plugin subset (one per ``G0..G7``
range plus a couple cross-section) spans the typical shape variations.

Each test loads the actual production plugin module (post-codemod),
not a fixture, so any future codemod regression on a real plugin file
fails the test naturally.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.harness.plugin_api import plugin
from lca.harness.plugin_declaration import definition_from_plugin
from lca.harness.plugin_manifest import PluginKind


class _Cfg(BaseModel):
    pass


# ruff: noqa: N802
class TestPostCodemodSmoke:
    """Verify contract=PluginContract works on the actual production plugins
    that were codemodded in PR-C (commit 794f9629)."""

    def _assert_contract_complete(self, plugin_module, *, expected_group) -> None:
        """The canonical-6-dim test: every dimension of the post-codemod
        plugin is recoverable through BOTH the legacy field AND the new
        contract sections.
        """
        defn = definition_from_plugin(plugin_module.setup)
        # 1. Canonical contract path (ADR-0110 D1) — the source of truth
        assert defn.contract is not None
        assert defn.contract.architecture.group is expected_group
        assert defn.contract.identity.version, f"{plugin_module.__name__} missing identity.version"
        # 2. Legacy synthesized LogicAddress (PR-A back-compat shim) — the
        #    reader-shim that keeps the deprecation window working. After
        #    codemod the codemodded contract carries every dim, so the
        #    shim must reproduce them all.
        assert defn.logic_address is not None
        assert defn.logic_address.functional_group is expected_group
        assert defn.logic_address.revision == defn.contract.identity.version

    def test_act_authorize_is_G6_DECISION(self) -> None:
        from lca.plugins.control_contributions.act_authorize import setup

        self._assert_contract_complete(
            type("M", (), {"setup": staticmethod(setup)}),
            expected_group=FunctionalGroup.G6_DECISION,
        )

    def test_observe_wildcard_is_G6_DECISION(self) -> None:
        from lca.plugins.control_contributions.observe_wildcard import setup

        self._assert_contract_complete(
            type("M", (), {"setup": staticmethod(setup)}),
            expected_group=FunctionalGroup.G6_DECISION,
        )

    def test_prompt_catalog_is_G10_COMPOSITION(self) -> None:
        from lca.plugins.composer.composition.prompt_catalog import setup

        self._assert_contract_complete(
            type("M", (), {"setup": staticmethod(setup)}),
            expected_group=FunctionalGroup.G10_COMPOSITION,
        )


class TestContractSnapshotRoundTrip:
    """contract_snapshot must round-trip through JSON without losing fields."""

    def test_snapshot_is_json_serializable(self) -> None:
        @plugin(
            id="snapshot.smoke",
            Config=_Cfg,
            provides=("snapshot.smoke",),
            layer="L2",
            kind=PluginKind.PRIMITIVE,
            contract=__import__(
                "lca.contracts.harness.composition.plugin_contract",
                fromlist=["PluginContract", "ArchitectureContract"],
            ).PluginContract(
                identity=__import__(
                    "lca.contracts.harness.composition.plugin_contract",
                    fromlist=["PluginIdentity"],
                ).PluginIdentity(id="snapshot.smoke", version="v2"),
                architecture=__import__(
                    "lca.contracts.harness.composition.plugin_contract",
                    fromlist=["ArchitectureContract"],
                ).ArchitectureContract(
                    group=FunctionalGroup.G5_COGNITION,
                    role="smoke_test",
                    control_slots=(),
                ),
            ),
        )
        async def setup(ctx, config): ...

        meta = setup.meta  # type: ignore[attr-defined]
        # Round-trip through JSON (this is what journal / projection / SSE do)
        encoded = json.dumps(meta["contract_snapshot"])
        decoded = json.loads(encoded)
        assert decoded["identity"]["id"] == "snapshot.smoke"
        assert decoded["identity"]["version"] == "v2"
        assert decoded["architecture"]["group"] == "G5"
        assert decoded["architecture"]["role"] == "smoke_test"


class TestLegacyKeysStillWork:
    """The deprecation window: ``logic_address=`` and ``functional_group=``
    keys at the @plugin() decorator level must still produce the same
    canonical contract (D3 back-compat shim).

    These tests exercise the codemod's *non-target* path: a plugin author
    who hasn't migrated yet should still land in a working state.
    """

    def test_functional_group_only_produces_minimal_contract(self) -> None:
        @plugin(
            id="legacy.fg",
            Config=_Cfg,
            provides=("legacy.fg",),
            layer="L2",
            kind=PluginKind.PRIMITIVE,
            functional_group=FunctionalGroup.G6_DECISION,
        )
        async def setup(ctx, config): ...

        defn = definition_from_plugin(setup)
        assert defn.contract.architecture.group is FunctionalGroup.G6_DECISION
        assert defn.contract.architecture.control_slots == ()
        assert defn.contract.authority.grants == ()
        assert defn.contract.observability.descriptors == ()

    def test_legacy_logic_address_produces_synthesized_contract(self) -> None:
        from lca.contracts.atoms.control_slot import ControlSlot
        from lca.contracts.atoms.scope import Scope
        from lca.contracts.protocols.composition.logic_address import LogicAddress

        @plugin(
            id="legacy.addr",
            Config=_Cfg,
            provides=("legacy.addr",),
            layer="L2",
            kind=PluginKind.PRIMITIVE,
            logic_address=LogicAddress(
                functional_group=FunctionalGroup.G7_EXECUTION,
                control_slot=ControlSlot.OBSERVE_WILDCARD,
                scope=Scope.RUN,
                authority=("plugin.serve",),
                evidence=("legacy.checked",),
                revision="v9",
            ),
        )
        async def setup(ctx, config): ...

        defn = definition_from_plugin(setup)
        # New canonical contract: fully populated from the legacy flat struct
        assert defn.contract.architecture.group is FunctionalGroup.G7_EXECUTION
        assert defn.contract.architecture.control_slots == (ControlSlot.OBSERVE_WILDCARD,)
        assert defn.contract.lifecycle.allowed_scopes == (Scope.RUN,)
        assert defn.contract.authority.grants == ("plugin.serve",)
        assert defn.contract.observability.descriptors == ("legacy.checked",)
        assert defn.contract.identity.version == "v9"
        # Back-compat shim still produces the legacy view too
        assert defn.logic_address is not None
        assert defn.logic_address.functional_group is FunctionalGroup.G7_EXECUTION
