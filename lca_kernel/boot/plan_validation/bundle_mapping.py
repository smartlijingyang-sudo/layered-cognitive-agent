"""Bundle-mapping resolution for boot-time plan validation.

The validator walks every plan referenced by a resolved profile.
These helpers load bundle YAML mappings, select the first
non-``.subgraph`` outer plan (mirroring ``plan_compile``'s
outer-plan selection), and recursively discover every inner
``sub_spec_ref`` subgraph plan reachable from it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from lca.framework.graph.lift.subgraph_contract import (
    _bundle_yaml_path,
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
    if nodes and not any(isinstance(n, dict) and n.get("entry") for n in nodes):
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
    base_dir: Path | None = None,
    path_resolver: Callable[[str], Path] | None = None,
    recurse: bool = False,
    visited: set[str] | None = None,
) -> list[tuple[Mapping[str, Any], str]]:
    """Yield inner plan mappings + ids for every ``sub_spec_ref`` the spec reaches.

    Each inner mapping has ``entry`` injected from the corresponding
    ``sub_spec_ref.entry_node`` (mirroring the lifter's
    :func:`_subgraph_entry_schema` behavior) so the inner plan's
    "exactly one entry node required" invariant passes — subgraph
    bundles legitimately omit ``entry`` because the outer plan tells
    the kernel where to start.

    Inner ``plan_ref`` paths resolve via :func:`lca.framework.graph.lifter._bundle_yaml_path`
    by default — joining them with the outer bundle's directory
    previously produced ``bundles/bundles/<inner>.yaml`` for
    production layouts and silently skipped every reachable subgraph
    (the prior bug). ``path_resolver`` is overridable so tests can
    pin resolution to ``tmp_path`` without polluting the production
    ``bundles/`` tree.

    With ``recurse=True`` the walker also descends into inner plans'
    own ``sub_spec_ref`` nodes, so a chained subgraph
    (``phase_main_outer.yaml`` → ``think.yaml`` → ``think_reason.yaml``
    → ``concept/tool_fork.yaml``) is validated in a single boot pass
    instead of failing at runtime when the inner-inner subgraph is
    first lifted. ``visited`` deduplicates by resolved plan id so
    shared subgraphs (referenced by more than one path) aren't
    re-lifted.
    """
    del base_dir  # kept for backward-compat with the prior signature
    resolver = path_resolver or _bundle_yaml_path
    inner: list[tuple[Mapping[str, Any], str]] = []
    seen: set[str] = set() if visited is None else visited
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
        if not plan_ref:
            continue
        try:
            inner_path = resolver(plan_ref)
        except (OSError, ValueError):
            continue
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
        if inner_id in seen:
            continue
        seen.add(inner_id)
        inner.append((spec, inner_id))
        if recurse:
            inner.extend(
                _subgraph_ref_with_entry(
                    spec,
                    path_resolver=resolver,
                    recurse=True,
                    visited=seen,
                )
            )
    return inner


__all__ = [
    "_apply_entry_fallback",
    "_bundle_base_dir",
    "_is_plan_spec",
    "_load_bundle_mapping",
    "_resolve_bundle_path",
    "_select_outer_plan",
    "_subgraph_ref_with_entry",
]
