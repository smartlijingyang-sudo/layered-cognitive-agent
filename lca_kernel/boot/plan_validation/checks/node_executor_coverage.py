"""Node-executor coverage check — boot-time fail-loud for orphan factories.

A bundle plan may declare ``node.factory: <name>`` (e.g.
``history.derive``) without any PluginSpec actually providing a
composite NodeExecutor key whose suffix matches. Pre-PR2 the kernel
only discovered this when the runtime interpreter entered the node
and :class:`NodeExecutorStrategy` raised
``NodeExecutor lookup miss`` at the broken hop — operators saw the
run die in the middle of ``think.main`` with a confusing registry
dump and no hint about which plugin entry was missing.

This check walks every plan reachable from the resolved profile
(outer plan + every ``sub_spec_ref`` subgraph, recursively) and
for every node whose ``factory`` field is non-empty, asserts that
some PluginSpec in the resolved profile declares a
:class:`CapabilityDeclaration` whose ``key`` ends with
``:: <factory>``. The composite-key ``<region>::<factory>`` is the
shape both the ``@graph_node`` decorator and the hand-written
``@plugin(...)`` modules under :mod:`lca.nodes.*` use to register
their NodeExecutor (see :func:`lca.plugins.composer.runtime.runtime.capabilities.resolve_node_executor_bindings`,
which already takes the suffix after ``::`` as the lookup key).

The check runs **before** the per-plan lifts complete so a missing
plugin entry fails boot with a clear message naming the missing
factory. It complements :func:`check_compiled_run_plan` (post-lift
K2 projection invariants) and the per-plan checks in
:data:`lca_kernel.boot.plan_validation._PLAN_CHECKS` (post-lift
graph-structural invariants).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.harness.profile.resolve.resolve import ResolvedProfile

_COMPOSITE_SEPARATOR = "::"


def _provided_factory_set(resolved: ResolvedProfile) -> dict[str, str]:
    """Map ``factory_name`` → plugin id for every enabled PluginSpec.

    Plugin authors register NodeExecutors under composite keys
    ``<region>::<factory>`` (see :mod:`lca.nodes._decorator` and
    the hand-written ``@plugin(...)`` modules). Multiple plugins
    can provide the same factory; the last one in resolution order
    wins, mirroring :func:`lca.plugins.composer.runtime.runtime.capabilities.resolve_node_executor_bindings`.
    """
    out: dict[str, str] = {}
    for plugin in resolved.plugins:
        if plugin.disabled:
            continue
        spec = plugin.definition.spec
        for offer in spec.provides:
            key = getattr(offer, "key", "")
            if _COMPOSITE_SEPARATOR not in key:
                continue
            factory = key.rsplit(_COMPOSITE_SEPARATOR, 1)[-1].strip()
            if not factory or _COMPOSITE_SEPARATOR in factory:
                continue
            out[factory] = plugin.id
    return out


def check_node_executor_coverage(
    bundles: Sequence[Mapping[str, Any]],
    resolved: ResolvedProfile,
) -> list[PlanLiftError]:
    """Every plan-reachable ``node.factory`` must have a PluginSpec provider.

    ``bundles`` is the sequence of raw bundle mappings the validator
    already lifts (outer plan + every inner ``sub_spec_ref`` subgraph,
    recursively). ``resolved`` carries the boot's resolved plugin
    set. The check ignores nodes with ``binding: <BindingKind>`` and
    ``sub_spec_ref`` (they are not leaf executors); only the
    legacy ``factory:`` style that maps to
    :class:`lca.contracts.protocols.graph.binding.BindingKind.NODE_EXECUTOR`
    is in scope.
    """
    errors: list[PlanLiftError] = []
    provided = _provided_factory_set(resolved)
    seen: set[str] = set()

    for mapping in bundles:
        if not isinstance(mapping, Mapping):
            continue
        plan_id = str(mapping.get("id", "<plan>"))
        if plan_id in seen:
            continue
        seen.add(plan_id)
        for raw in mapping.get("nodes", ()) or ():
            if not isinstance(raw, Mapping):
                continue
            # Subgraph delegates are not leaf executors; the inner
            # plan is validated on its own pass. The lifter probes
            # both the top-level ``sub_spec_ref`` and the legacy
            # ``config.sub_spec_ref`` shape (see
            # :func:`lca.framework.graph.lifter._binding_from_factory_or_binding`),
            # so the check must mirror that to avoid false positives
            # for nodes whose ``factory`` is purely an outer alias.
            config = raw.get("config")
            has_sub_spec = raw.get("sub_spec_ref") is not None or (
                isinstance(config, Mapping) and config.get("sub_spec_ref") is not None
            )
            if has_sub_spec:
                continue
            factory = raw.get("factory")
            if not isinstance(factory, str) or not factory.strip():
                continue
            factory = factory.strip()
            provider = provided.get(factory)
            if provider is not None:
                continue
            errors.append(
                PlanLiftError(
                    f"plan {plan_id!r}: node {raw.get('id', '<unnamed>')!r} "
                    f"declares factory={factory!r} but no enabled plugin "
                    f"in the resolved profile provides a NodeExecutor "
                    f"under the composite key `<region>::{factory}`. "
                    f"Add the missing plugin to a profile bundle (e.g. "
                    f"``- id: phase.<region>.{factory}`` in ``bundles/...``) "
                    f"or remove the node from the bundle.",
                    plan_id=plan_id,
                    node_id=str(raw.get("id", "<unnamed>")),
                )
            )
    return errors


__all__ = ["check_node_executor_coverage"]
