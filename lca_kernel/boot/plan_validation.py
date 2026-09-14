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
"""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from lca.contracts.protocols.graph.errors import PlanLiftError
from lca.framework.graph.lifter import lift_graph_spec
from lca.harness.profile.resolve.resolve import ResolvedProfile


def validate_profile_plans(resolved: ResolvedProfile) -> None:
    """Lift every plan reachable from ``resolved`` and aggregate failures.

    The validator mirrors :func:`lca_kernel.plan.plan_compile._wrap_v2_plan`'s
    outer-plan selection (first non-``.subgraph`` bundle, with
    first-node-as-entry fallback) and recursively validates every
    subgraph plan reachable via :class:`SubgraphReference`. Aggregated
    :class:`PlanLiftError` instances are joined into a single failure
    with ``plan_id`` set to the profile name so the kernel refuses to
    start.

    On success, a one-line ``✅`` message is written to stderr so the
    count surfaces in ``/tmp/lca-kernel.log``.
    """
    bundles: Sequence[str] = getattr(resolved, "bundles", ()) or ()
    if not bundles:
        return  # empty profile — nothing to validate

    profile_name = Path(resolved.profile_path).name or "<profile>"
    profile_dir = Path(resolved.profile_path).parent
    failures: list[PlanLiftError] = []
    validated = 0

    outer_mapping, outer_path = _select_outer_plan(bundles, profile_dir=profile_dir)
    if outer_mapping is None:
        return  # no plan-shaped bundle in this profile

    plan_id = str(outer_mapping.get("id", outer_path.stem if outer_path else "<plan>"))
    # String DSL must fail loud even when the lifter silently coerces it.
    string_err = _check_string_predicate(outer_mapping, plan_id=plan_id)
    if string_err is not None:
        failures.append(string_err)
    else:
        outer_with_entry = _apply_entry_fallback(outer_mapping)
        err = _safe_lift(outer_with_entry)
        if err is not None:
            failures.append(_annotate(err, plan_id=plan_id))
        else:
            validated += 1
    # Always recurse into inner sub_spec_ref plans so the user sees
    # all problems at once (per the "aggregate errors" contract).
    for inner_mapping, inner_id in _subgraph_ref_with_entry(
        outer_mapping,
        base_dir=_bundle_base_dir(outer_path, profile_dir=profile_dir),
    ):
        inner_string_err = _check_string_predicate(inner_mapping, plan_id=inner_id)
        if inner_string_err is not None:
            failures.append(inner_string_err)
            continue
        inner_err = _safe_lift(inner_mapping)
        if inner_err is not None:
            failures.append(_annotate(inner_err, plan_id=inner_id))
            continue
        validated += 1

    if failures:
        raise _aggregate(failures, profile_name=profile_name)

    print(
        f"✅ profile {profile_name}: {validated} plans validated",
        file=sys.stderr,
    )


def _select_outer_plan(
    bundles: Sequence[str],
    *,
    profile_dir: Path,
) -> tuple[Mapping[str, Any] | None, Path | None]:
    """Return the first non-``.subgraph`` bundle mapping and resolved path.

    Mirrors :func:`lca_kernel.plan.plan_compile._wrap_v2_plan`: phase
    subgraph bundles (id ends with ``.subgraph``) are entered through
    :class:`SubgraphReference` rather than executed as the outer plan,
    so the validator skips them at the top level. Subgraph plans are
    still validated when reached via ``sub_spec_ref`` from the outer.
    """
    for entry in bundles:
        mapping = _load_bundle_mapping(entry, profile_dir=profile_dir)
        if mapping is None:
            continue
        if not _is_plan_spec(mapping):
            continue
        bundle_id = str(mapping.get("id", ""))
        if bundle_id.endswith(".subgraph"):
            continue
        path = _resolve_bundle_path(entry, profile_dir=profile_dir)
        return mapping, path
    return None, None


def _load_bundle_mapping(
    bundle_path: str,
    *,
    profile_dir: Path,
) -> Mapping[str, Any] | None:
    """Load a bundle yaml as a mapping. Returns None on missing/invalid files."""
    path = _resolve_bundle_path(bundle_path, profile_dir=profile_dir)
    if path is None or not path.exists():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _resolve_bundle_path(bundle_path: str, *, profile_dir: Path) -> Path | None:
    """Resolve a bundle path to a real filesystem path (CWD first, then profile_dir)."""
    path = Path(bundle_path)
    if path.is_absolute():
        return path
    candidate = Path.cwd() / bundle_path
    if candidate.exists():
        return candidate
    candidate = profile_dir / bundle_path
    if candidate.exists():
        return candidate
    return path  # return as-is so callers can detect "not found"


def _is_plan_spec(mapping: Mapping[str, Any]) -> bool:
    """A v2 plan spec declares ``nodes``/``edges`` at the bundle root."""
    return "nodes" in mapping or "edges" in mapping


def _apply_entry_fallback(mapping: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of *mapping* with ``entry`` set if no node marks one.

    Mirrors :func:`lca_kernel.plan.plan_compile._wrap_v2_plan`'s
    first-node-as-entry fallback so the v2 Plan constructor's
    "exactly one entry" rule passes for legacy bundles that omit it.
    """
    spec = dict(mapping)
    nodes = list(spec.get("nodes") or ())
    if nodes and not any(
        isinstance(n, dict) and n.get("entry") for n in nodes
    ):
        nodes[0] = {**nodes[0], "entry": True}
        spec["nodes"] = nodes
    return spec


def _bundle_base_dir(bundle_path: Path | None, *, profile_dir: Path) -> Path:
    """Return the directory a bundle path resolves to, for resolving
    relative ``sub_spec_ref.plan_ref`` entries against it.
    """
    if bundle_path is None:
        return profile_dir
    return bundle_path.parent


def _subgraph_ref_with_entry(
    mapping: Mapping[str, Any],
    *,
    base_dir: Path,
) -> list[tuple[Mapping[str, Any], str]]:
    """Yield inner plan mappings + ids for every ``sub_spec_ref`` the spec reaches.

    Each inner mapping has ``entry`` injected from the corresponding
    ``sub_spec_ref.entry_node`` (mirroring the lifter's
    :func:`_subgraph_entry_schema` behavior) so the inner plan's
    "exactly one entry node required" invariant passes — subgraph
    bundles legitimately omit ``entry`` because the outer plan tells
    the kernel where to start.
    """
    inner: list[tuple[Mapping[str, Any], str]] = []
    seen: set[str] = set()
    for raw in mapping.get("nodes", ()) or ():
        if not isinstance(raw, Mapping):
            continue
        sub_ref = raw.get("sub_spec_ref")
        if sub_ref is None:
            config = raw.get("config")
            if isinstance(config, Mapping):
                sub_ref = config.get("sub_spec_ref")
        if not isinstance(sub_ref, Mapping):
            continue
        plan_ref = str(sub_ref.get("plan_ref", "")).strip()
        entry_node = str(sub_ref.get("entry_node", "")).strip()
        if not plan_ref or plan_ref in seen:
            continue
        seen.add(plan_ref)
        inner_path = base_dir / plan_ref
        if not inner_path.exists():
            continue
        try:
            raw_inner = yaml.safe_load(inner_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(raw_inner, dict):
            continue
        spec = dict(raw_inner)
        if "entry" not in spec and entry_node:
            spec["entry"] = entry_node
        inner_id = str(spec.get("id", plan_ref))
        inner.append((spec, inner_id))
    return inner


# Strings that the lifter's :func:`_coerce_when` maps to ``None`` —
# the predicates evaluate to "always true" at runtime, but the legacy
# string DSL (``when: result.payload...``) is no longer supported and
# silently fires every edge regardless of the upstream decision. We
# fail loud at boot so a misroute never reaches runtime.
_STRING_WHEN_ALIASES = frozenset({"true", "false", ""})


def _check_string_predicate(
    spec: Mapping[str, Any],
    *,
    plan_id: str,
) -> PlanLiftError | None:
    """Build a :class:`PlanLiftError` for a string-predicate edge, or None."""
    for raw in spec.get("edges", ()) or ():
        if not isinstance(raw, Mapping):
            continue
        when = raw.get("when")
        if isinstance(when, str) and when.strip().lower() not in _STRING_WHEN_ALIASES:
            edge_id = f"{raw.get('from', '?')}->{raw.get('to', '?')}"
            return PlanLiftError(
                f"plan {plan_id!r}: edge {edge_id!r}: string when: {when!r} is no longer supported; "
                "use a typed Predicate dict",
                plan_id=plan_id,
                edge_id=edge_id,
            )
    return None


def _aggregate(
    failures: list[PlanLiftError],
    *,
    profile_name: str,
) -> PlanLiftError:
    """Combine every per-plan failure into one :class:`PlanLiftError`."""
    lines: list[str] = []
    for err in failures:
        lines.append(f"- {err}")
    joined = "\n".join(lines)
    return PlanLiftError(
        f"profile {profile_name}: {len(failures)} plan(s) lifted with errors:\n{joined}",
        plan_id=profile_name,
    )


def _annotate(err: PlanLiftError, *, plan_id: str) -> PlanLiftError:
    """Re-raise *err* with the plan id in both the message and the
    structured ``plan_id`` field.

    The lifter already sets ``plan_id`` on most errors; we always
    prepend the plan id to the message so the aggregated reason is
    self-describing when multiple plans fail at once.
    """
    return PlanLiftError(
        f"plan {plan_id!r}: {err}",
        plan_id=plan_id,
        node_id=err.node_id,
        edge_id=err.edge_id,
        port_name=err.port_name,
    )


def _safe_lift(spec: Mapping[str, Any]) -> PlanLiftError | None:
    """Run :func:`lift_graph_spec` and normalize any failure to
    :class:`PlanLiftError`.
    """
    try:
        lift_graph_spec(spec)
        return None
    except PlanLiftError as exc:
        return exc
    except ValidationError as exc:
        return PlanLiftError(str(exc))


__all__ = ["validate_profile_plans"]
