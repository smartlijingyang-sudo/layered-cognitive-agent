"""Tests for :func:`check_node_executor_coverage`.

Three cases cover the boot-time fail-loud for orphan factories:

- plan node declares ``factory: <X>`` and the profile's resolved
  plugins include a spec providing ``<region>::<X>`` → pass
- plan node declares ``factory: <X>`` and no resolved plugin
  provides the matching composite key → reject with a clear
  message naming the missing factory
- plan node with ``config.sub_spec_ref`` is treated as a subgraph
  delegate, not a leaf executor → no error (its inner plan is
  validated on its own pass)

The check runs pre-lift on raw bundle mappings; we synthesize the
mappings inline rather than going through :func:`lift_graph_spec`,
which would discard ``factory`` after mapping it to
``BindingKind.NODE_EXECUTOR``.

The check only reads :attr:`ResolvedPlugin.definition.spec.provides`
so the test plugin mocks build just enough of that shape.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    PLUGIN_SPEC_VERSION,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    CapabilityDeclaration,
    PluginSpec,
    PluginSpecKind,
)
from lca.harness.profile.resolve.resolve import ResolvedProfile
from lca_kernel.boot.plan_validation.checks.node_executor_coverage import (
    check_node_executor_coverage,
)


def _spec(*provides: str) -> PluginSpec:
    """Build a minimal PluginSpec providing the given composite keys.

    PluginSpec's ``__post_init__`` validates api_version, kind, and
    effects against the closed sets; we satisfy those with real enum
    values and use MagicMock for the rest since the check only reads
    ``provides``.
    """
    return PluginSpec(
        api_version=PLUGIN_SPEC_VERSION,
        id="phase.test.dummy",
        revision="v1",
        kind=PluginSpecKind.SEAM,
        layer="L2",
        functional_group="G7_EXECUTION",
        implementation=MagicMock(),
        configuration=MagicMock(),
        provides=tuple(
            CapabilityDeclaration(key=key, cardinality="one") for key in provides
        ),
        requires=(),
        effects=("none",),
        ownership=MagicMock(),
        lifecycle=MagicMock(),
        relations=(),
        evidence=MagicMock(),
        verification=MagicMock(),
    )


def _plugin(plugin_id: str, spec: PluginSpec) -> MagicMock:
    p = MagicMock()
    p.id = plugin_id
    p.disabled = False
    p.definition.spec = spec
    return p


def _resolved(*plugins: MagicMock) -> ResolvedProfile:
    return ResolvedProfile(
        profile_path="<test>",
        bundles=(),
        plugins=tuple(plugins),
        dag_edges=(),
        manifest_hash="0" * 64,
        env_refs=(),
    )


def test_missing_factory_rejected_with_clear_message() -> None:
    """A plan node whose factory has no provider must fail with the factory name."""
    spec = _spec("think::think.shortcut")
    resolved = _resolved(_plugin("phase.think.shortcut", spec))
    bundle: dict[str, Any] = {
        "id": "plan.with.missing",
        "nodes": [
            {
                "id": "orphan.node",
                "factory": "history.derive",
            }
        ],
        "edges": [],
    }

    errors = check_node_executor_coverage([bundle], resolved)

    assert len(errors) == 1
    err = errors[0]
    assert "history.derive" in str(err)
    assert err.plan_id == "plan.with.missing"
    assert err.node_id == "orphan.node"


def test_provided_factory_passes() -> None:
    """A plan node whose factory is provided by an enabled plugin → no error."""
    spec = _spec("think::history.derive")
    resolved = _resolved(_plugin("phase.think.history.derive", spec))
    bundle: dict[str, Any] = {
        "id": "plan.with.provider",
        "nodes": [
            {
                "id": "history.derive",
                "factory": "history.derive",
            }
        ],
        "edges": [],
    }

    assert check_node_executor_coverage([bundle], resolved) == []


def test_subgraph_delegate_with_config_sub_spec_ref_is_not_a_leaf() -> None:
    """Nodes with ``config.sub_spec_ref`` are subgraph delegates; not leaf executors."""
    spec = _spec("think::think.shortcut")
    resolved = _resolved(_plugin("phase.think.shortcut", spec))
    bundle: dict[str, Any] = {
        "id": "plan.with.delegate",
        "nodes": [
            {
                "id": "outer.delegate",
                "factory": "outer.factory.name",  # not in the spec list
                "config": {
                    "sub_spec_ref": {
                        "plan_ref": "bundles/inner.yaml",
                        "entry_node": "inner.entry",
                    }
                },
            }
        ],
        "edges": [],
    }

    # factory is unregistered, but the node delegates to a subgraph
    # so the check must skip it — the inner plan's own pass owns it.
    assert check_node_executor_coverage([bundle], resolved) == []
