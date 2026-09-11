"""BundleGraphNode sub_spec_ref + yaml parser tests (ADR-0219 §10.11 item 1).

Contract:
- BundleGraphNode has a typed ``sub_spec_ref: SubgraphReference | None = None``.
- __post_init__ validates that the value, when not None, is a
  SubgraphReference instance.
- _load_bundle_graph_spec parses yaml config.sub_spec_ref into a typed
  SubgraphReference and stores it on the typed field; config does NOT
  retain sub_spec_ref as a key after parsing.
- Missing required fields raise DeclarativeValidationError (PG-004).
- Wrong shape (non-Mapping) raises DeclarativeValidationError (PG-004).
"""

from __future__ import annotations

import pytest

from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.harness.declarative.compile.subgraph_resolver import (
    _load_bundle_graph_spec,
    _parse_sub_spec_ref,
)


class TestBundleGraphNodeSubSpecRef:
    def test_default_is_none(self) -> None:
        node = BundleGraphNode(id="n", region="r", factory="f")
        assert node.sub_spec_ref is None

    def test_accepts_typed_subgraph_reference(self) -> None:
        ref = SubgraphReference(
            plan_ref="bundles/x.yaml",
            entry_node="x.entry",
            binding_edge="n",
        )
        node = BundleGraphNode(
            id="n",
            region="r",
            factory="f",
            sub_spec_ref=ref,
        )
        assert node.sub_spec_ref is ref

    def test_rejects_non_subgraph_reference(self) -> None:
        with pytest.raises(DeclarativeValidationError) as excinfo:
            BundleGraphNode(
                id="n",
                region="r",
                factory="f",
                sub_spec_ref={"plan_ref": "x"},  # type: ignore[arg-type]
            )
        assert excinfo.value.code == "PG-005-bundle-graph"


class TestParseSubSpecRefHelper:
    def test_none_returns_none(self) -> None:
        assert _parse_sub_spec_ref(None) is None

    def test_valid_mapping(self) -> None:
        ref = _parse_sub_spec_ref(
            {
                "plan_ref": "bundles/x.yaml",
                "entry_node": "x.entry",
                "binding_edge": "n",
            }
        )
        assert isinstance(ref, SubgraphReference)
        assert ref.plan_ref == "bundles/x.yaml"
        assert ref.entry_node == "x.entry"
        assert ref.binding_edge == "n"

    def test_non_mapping_raises(self) -> None:
        with pytest.raises(DeclarativeValidationError) as excinfo:
            _parse_sub_spec_ref("not-a-mapping")  # type: ignore[arg-type]
        assert excinfo.value.code == "PG-004"

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(DeclarativeValidationError) as excinfo:
            _parse_sub_spec_ref({"plan_ref": "x", "entry_node": "y"})
        assert excinfo.value.code == "PG-004"


class TestYamlLoaderStripsSubSpecRef:
    def test_yaml_sub_spec_ref_parsed_to_typed_field(self) -> None:
        spec = _load_bundle_graph_spec("bundles/think.yaml")
        reason_node = next(n for n in spec.nodes if n.id == "think.reason")
        assert reason_node.sub_spec_ref is not None
        assert reason_node.sub_spec_ref.plan_ref == "bundles/think_reason.yaml"
        assert reason_node.sub_spec_ref.entry_node == "think.reason.plan"
        assert reason_node.sub_spec_ref.binding_edge == "think.reason"
        # config MUST NOT retain sub_spec_ref as a key after parsing
        assert "sub_spec_ref" not in reason_node.config

    def test_yaml_node_without_sub_spec_ref_stays_none(self) -> None:
        """Nodes without ``sub_spec_ref`` in the yaml must keep ``sub_spec_ref``
        as ``None`` after parsing. ADR-0220 P6 moved think.classify and
        think.gate to ``sub_spec_ref`` delegates — those are excluded
        from this check; only the pure-inline nodes (shortcut, route)
        must satisfy the invariant.
        """
        inline_only = {"think.reason", "think.classify", "think.gate"}
        spec = _load_bundle_graph_spec("bundles/think.yaml")
        for n in spec.nodes:
            if n.id in inline_only:
                continue
            assert n.sub_spec_ref is None, f"unexpected sub_spec_ref on inline node {n.id!r}"
            assert "sub_spec_ref" not in n.config

    def test_inner_bundle_yaml_has_no_sub_spec_ref(self) -> None:
        spec = _load_bundle_graph_spec("bundles/think_reason.yaml")
        for n in spec.nodes:
            assert n.sub_spec_ref is None
            assert "sub_spec_ref" not in n.config
