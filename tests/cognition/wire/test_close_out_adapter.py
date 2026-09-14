"""Tests for CloseOutAdapter — generic subgraph → outer port translation.

The adapter is the D10 ACL: it shrinks the legacy CLOSE_OUT_REGISTRY
projection to a port-by-port copy with an optional rename map.
"""

from __future__ import annotations

from typing import Any

from lca.cognition.wire.close_out_adapter import CloseOutAdapter
from lca.contracts.protocols.graph.node_io import PortSpec
from lca.contracts.protocols.graph.ports import PortName
from lca.framework.graph.port_registry import PortRegistry


def _spec(name: str) -> PortSpec:
    return PortSpec(name=PortName(name))


class TestSameNameForwarding:
    def test_forwards_each_declared_output(self) -> None:
        registry = PortRegistry()
        registry.merge_output(
            {
                PortName("decision"): "decision_value",
                PortName("observation"): "observation_value",
            }
        )
        outer_outputs = (_spec("decision"), _spec("observation"))

        result = CloseOutAdapter().close_out(inner_registry=registry, outer_outputs=outer_outputs)

        assert result == {
            PortName("decision"): "decision_value",
            PortName("observation"): "observation_value",
        }

    def test_forwards_complex_payloads_unchanged(self) -> None:
        payload = {"kind": "decision", "action_type": "use_tool"}
        registry = PortRegistry()
        registry.set_typed_port(PortName("decision"), payload, payload_type=dict)
        outer_outputs = (_spec("decision"),)

        result = CloseOutAdapter().close_out(inner_registry=registry, outer_outputs=outer_outputs)

        assert result == {PortName("decision"): payload}


class TestRenameMap:
    def test_rename_forwarding(self) -> None:
        registry = PortRegistry()
        registry.merge_output({PortName("observation"): "obs_value"})
        outer_outputs = (_spec("act_outcome"),)

        adapter = CloseOutAdapter(rename_map={PortName("act_outcome"): PortName("observation")})
        result = adapter.close_out(inner_registry=registry, outer_outputs=outer_outputs)

        assert result == {PortName("act_outcome"): "obs_value"}

    def test_rename_does_not_pollute_inner_name(self) -> None:
        registry = PortRegistry()
        registry.merge_output({PortName("observation"): "obs_value"})
        outer_outputs = (_spec("act_outcome"), _spec("observation"))

        adapter = CloseOutAdapter(rename_map={PortName("act_outcome"): PortName("observation")})
        result = adapter.close_out(inner_registry=registry, outer_outputs=outer_outputs)

        assert result == {
            PortName("act_outcome"): "obs_value",
            PortName("observation"): "obs_value",
        }

    def test_partial_rename_mix_with_same_name(self) -> None:
        registry = PortRegistry()
        registry.merge_output(
            {
                PortName("observation"): "obs_value",
                PortName("reflection"): "ref_value",
            }
        )
        outer_outputs = (_spec("act_outcome"), _spec("reflection"))

        adapter = CloseOutAdapter(rename_map={PortName("act_outcome"): PortName("observation")})
        result = adapter.close_out(inner_registry=registry, outer_outputs=outer_outputs)

        assert result == {
            PortName("act_outcome"): "obs_value",
            PortName("reflection"): "ref_value",
        }


class TestMissingInnerPort:
    def test_missing_inner_port_yields_no_entry(self) -> None:
        registry = PortRegistry()
        registry.merge_output({PortName("decision"): "decision_value"})
        outer_outputs = (_spec("decision"), _spec("observation"))

        result = CloseOutAdapter().close_out(inner_registry=registry, outer_outputs=outer_outputs)

        assert result == {PortName("decision"): "decision_value"}
        assert PortName("observation") not in result

    def test_empty_registry_returns_empty_dict(self) -> None:
        registry = PortRegistry()
        outer_outputs = (_spec("decision"), _spec("observation"))

        result = CloseOutAdapter().close_out(inner_registry=registry, outer_outputs=outer_outputs)

        assert result == {}

    def test_rename_to_missing_inner_port_yields_no_entry(self) -> None:
        registry = PortRegistry()
        outer_outputs = (_spec("act_outcome"),)

        adapter = CloseOutAdapter(rename_map={PortName("act_outcome"): PortName("observation")})
        result = adapter.close_out(inner_registry=registry, outer_outputs=outer_outputs)

        assert result == {}


class TestEdgeCases:
    def test_empty_outer_outputs_returns_empty_dict(self) -> None:
        registry = PortRegistry()
        registry.merge_output({PortName("decision"): "decision_value"})

        result = CloseOutAdapter().close_out(inner_registry=registry, outer_outputs=())

        assert result == {}

    def test_uses_has_port_not_keyerror(self) -> None:
        """The adapter must call has_port before read so unset ports don't raise."""

        class RaisingRegistry:
            def __init__(self) -> None:
                self._data: dict[PortName, Any] = {PortName("decision"): "d"}

            def has_port(self, name: PortName) -> bool:
                return name in self._data

            def read(self, name: PortName) -> Any:
                # Real PortRegistry.read raises UnsetPortError on missing.
                if name not in self._data:
                    raise KeyError(name)
                return self._data[name]

        outer_outputs = (_spec("decision"), _spec("observation"))
        result = CloseOutAdapter().close_out(
            inner_registry=RaisingRegistry(), outer_outputs=outer_outputs
        )

        assert result == {PortName("decision"): "d"}
