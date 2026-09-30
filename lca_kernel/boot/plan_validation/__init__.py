"""Boot-time plan validation — fail-loud gate for malformed plans.

The kernel walks every plan referenced by a resolved profile and lifts
each one through :func:`lift_graph_spec`. Any :class:`PlanLiftError`
raises immediately so a malformed plan is caught at kernel startup,
not 5 minutes into the first run when the user notices the run failed.

Errors are **aggregated** across all plans before raising, so the
operator sees every problem in a single boot failure rather than
fixing them one at a time.

The hook is wired into :func:`lca_kernel.boot.boot.run_resolved_kernel`
between K2 (``compile_run_plan``) and K3 (``_boot_context``). It runs
on every boot including tests and minimal paths — the only escape is
when the profile carries no bundles (empty profile is a no-op).

This package is split into focused submodules (``core``,
``bundle_mapping``, ``predicates``, ``typed_ports``, ``reachability``);
this module re-exports the historical surface so existing importers
keep working unchanged.
"""

from lca.framework.graph.lift.subgraph_contract import (
    _bundle_yaml_path as _bundle_yaml_path,
)
from lca_kernel.boot.plan_validation.bundle_mapping import (
    _apply_entry_fallback as _apply_entry_fallback,
)
from lca_kernel.boot.plan_validation.bundle_mapping import (
    _bundle_base_dir as _bundle_base_dir,
)
from lca_kernel.boot.plan_validation.bundle_mapping import (
    _is_plan_spec as _is_plan_spec,
)
from lca_kernel.boot.plan_validation.bundle_mapping import (
    _load_bundle_mapping as _load_bundle_mapping,
)
from lca_kernel.boot.plan_validation.bundle_mapping import (
    _resolve_bundle_path as _resolve_bundle_path,
)
from lca_kernel.boot.plan_validation.bundle_mapping import (
    _select_outer_plan as _select_outer_plan,
)
from lca_kernel.boot.plan_validation.bundle_mapping import (
    _subgraph_ref_with_entry as _subgraph_ref_with_entry,
)
from lca_kernel.boot.plan_validation.checks.admit_recovery_edge import (
    AdmitRecoveryEdgeCheck as AdmitRecoveryEdgeCheck,
)
from lca_kernel.boot.plan_validation.checks.compiled_run_plan import (
    check_compiled_run_plan as check_compiled_run_plan,
)
from lca_kernel.boot.plan_validation.checks.cycle_port_dependency import (
    CyclePortDependencyCheck as CyclePortDependencyCheck,
)
from lca_kernel.boot.plan_validation.checks.cycle_terminal import (
    CycleHasTerminalCheck as CycleHasTerminalCheck,
)
from lca_kernel.boot.plan_validation.checks.entry_uniqueness import (
    EntryUniquenessCheck as EntryUniquenessCheck,
)
from lca_kernel.boot.plan_validation.checks.node_executor_coverage import (
    check_node_executor_coverage as check_node_executor_coverage,
)
from lca_kernel.boot.plan_validation.checks.predicate_wellformed import (
    PredicateWellformedCheck as PredicateWellformedCheck,
)
from lca_kernel.boot.plan_validation.checks.profile_topology import (
    check_profile_topology as check_profile_topology,
)
from lca_kernel.boot.plan_validation.checks.subgraph_port_contract import (
    SubgraphPortContractCheck as SubgraphPortContractCheck,
)
from lca_kernel.boot.plan_validation.checks.use_tool_reask_edge import (
    UseToolReaskEdgeCheck as UseToolReaskEdgeCheck,
)
from lca_kernel.boot.plan_validation.core import (
    _PLAN_CHECKS as _PLAN_CHECKS,
)
from lca_kernel.boot.plan_validation.core import (
    _aggregate as _aggregate,
)
from lca_kernel.boot.plan_validation.core import (
    _annotate as _annotate,
)
from lca_kernel.boot.plan_validation.core import (
    _check_lifted_plan as _check_lifted_plan,
)
from lca_kernel.boot.plan_validation.core import (
    _check_plan_spec as _check_plan_spec,
)
from lca_kernel.boot.plan_validation.core import (
    _lift_with_optional_termination as _lift_with_optional_termination,
)
from lca_kernel.boot.plan_validation.core import (
    _normalize as _normalize,
)
from lca_kernel.boot.plan_validation.core import (
    _safe_lift as _safe_lift,
)
from lca_kernel.boot.plan_validation.core import (
    validate_profile_plans as validate_profile_plans,
)
from lca_kernel.boot.plan_validation.predicates import (
    _STRING_WHEN_ALIASES as _STRING_WHEN_ALIASES,
)
from lca_kernel.boot.plan_validation.predicates import (
    _check_string_predicate as _check_string_predicate,
)
from lca_kernel.boot.plan_validation.reachability import (
    _check_cycle_has_terminal as _check_cycle_has_terminal,
)
from lca_kernel.boot.plan_validation.reachability import (
    _check_reachability as _check_reachability,
)
from lca_kernel.boot.plan_validation.reachability import (
    _check_terminal_no_outgoing_edges as _check_terminal_no_outgoing_edges,
)
from lca_kernel.boot.plan_validation.reachability import (
    _check_terminal_reachable_from_entry as _check_terminal_reachable_from_entry,
)
from lca_kernel.boot.plan_validation.typed_ports import (
    _check_typed_port_wiring as _check_typed_port_wiring,
)

__all__ = ["validate_profile_plans"]
