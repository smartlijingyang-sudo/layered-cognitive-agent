"""Round 88 regression: ``CAPABILITIES_BY_KEY`` index covers every named
Capability, identity-preserving, with no phantom keys.
"""

from __future__ import annotations

from lca.contracts.capabilities import (
    CAPABILITIES_BY_KEY,
    LLM,
    TOOLS,
    TRANSPORT,
    Capability,
)


class TestCapabilityIndex:
    def test_index_is_nonempty(self) -> None:
        assert len(CAPABILITIES_BY_KEY) > 50  # 80+ capabilities registered

    def test_index_covers_known_constants(self) -> None:
        assert CAPABILITIES_BY_KEY["llm"] is LLM
        assert CAPABILITIES_BY_KEY["tools"] is TOOLS
        assert CAPABILITIES_BY_KEY["transport"] is TRANSPORT

    def test_index_keys_are_unique(self) -> None:
        keys = list(CAPABILITIES_BY_KEY.keys())
        assert len(keys) == len(set(keys))

    def test_index_values_are_capability_instances(self) -> None:
        for value in CAPABILITIES_BY_KEY.values():
            assert isinstance(value, Capability)

    def test_index_keys_match_capability_keys(self) -> None:
        for key, cap in CAPABILITIES_BY_KEY.items():
            assert cap.key == key

    def test_no_legacy_run_loop_driver_registry_alias(self) -> None:
        """R88: dead alias RUN_LOOP_DRIVER_REGISTRY = DRIVERS removed."""
        import lca.contracts.capabilities as caps

        assert not hasattr(caps, "RUN_LOOP_DRIVER_REGISTRY")

    def test_drivers_still_in_index(self) -> None:
        """Sanity: the canonical name (DRIVERS) still resolves."""
        assert "run_loop_driver_registry" in CAPABILITIES_BY_KEY
