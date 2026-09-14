"""Profile-level bundle topology check.

Reject malformed profile bundle topology *before* the plan-level
lifter walks each bundle. ``validate_profile_plans`` already
validates every plan reachable from a resolved profile; this
check is the structural layer above it — it inspects the
profile's own bundle list and rejects defects that the
plan-level checks cannot see (duplicate paths, reserved ids,
underscore-prefixed stems).

Why a free function instead of a :class:`PlanCheck` subclass?
-------------------------------------------------------------

Every other check in this package operates on a lifted
:class:`Plan`; the ``PlanCheck`` protocol is
``(plan: Plan) -> PlanLiftError | None``. Profile topology
operates on the profile's raw bundle *path list* before any
plan is lifted — it does not have a :class:`Plan` to inspect.
A subclass would force the call site to manufacture a
placeholder plan, leaking profile-level concerns into the
plan-level surface. A free function keeps the seam honest:
``check_profile_topology`` is called from
:func:`validate_profile_plans` with the resolved profile's
``bundles`` tuple, and its errors are aggregated into the
existing :func:`_aggregate` failure.
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.protocols.graph.errors import PlanLiftError

# Bundle ids that collide with Python / pytest internals. A bundle
# named ``__init__`` would shadow Python package semantics, ``test``
# / ``fixture`` / ``conftest`` would be picked up by pytest's test
# discovery and try to import the bundle as a Python module. Reject
# up front so a typo'd bundle id fails boot instead of silently
# breaking test discovery or import resolution later.
_RESERVED_BUNDLE_IDS: frozenset[str] = frozenset(
    {"__init__", "test", "fixture", "conftest"}
)


def check_profile_topology(
    bundle_paths: tuple[str, ...],
    *,
    profile_name: str = "<profile>",
) -> list[PlanLiftError]:
    """Reject malformed profile bundle topology.

    Runs at boot before plan-level checks so a broken profile
    surfaces immediately with a structural message rather than
    a downstream graph-confusion error. The function is
    deliberately narrow: it only inspects the profile's own
    bundle path list and never descends into any individual
    bundle's plan — that work belongs to
    :func:`lca_kernel.boot.plan_validation.validate_profile_plans`.

    The three defect classes caught here are:

    1. **Duplicate bundle paths** — the same bundle referenced
       twice produces two lift attempts of the same plan,
       double-counting the plan in the validated total and
       risking subtle ordering bugs if the lift result is
       cached per path.
    2. **Empty bundle id** — a path like ``bundles/.yaml`` or
       ``bundles//foo`` resolves to a stem of ``""`` and
       cannot be referenced by other plans via a stable id.
    3. **Reserved / underscore-prefixed bundle ids** — ids
       colliding with Python (``__init__``) or pytest
       (``test`` / ``fixture`` / ``conftest``) internals, or
       starting with ``_`` (a Python-private convention that
       should not leak into user-facing bundle ids).

    Returns an empty list when the topology is clean; the
    caller is responsible for aggregating and raising.
    """
    errors: list[PlanLiftError] = []

    # 1. Duplicate bundle paths
    seen: set[str] = set()
    duplicates: list[str] = []
    for bundle_path in bundle_paths:
        if bundle_path in seen:
            duplicates.append(bundle_path)
        else:
            seen.add(bundle_path)
    if duplicates:
        errors.append(
            PlanLiftError(
                f"profile {profile_name}: duplicate bundle paths in "
                f"profile: {duplicates!r}; each bundle should be "
                f"referenced once",
                plan_id=profile_name,
            )
        )

    # 2. Empty bundle id — a trailing slash, a path ending in the
    #    yaml extension with no stem (``bundles/.yaml`` where
    #    ``Path.stem`` is ``'.yaml'`` because POSIX treats it as
    #    a hidden-file name rather than an empty stem), or any
    #    other shape that yields an empty ``Path.stem`` cannot
    #    serve as a stable bundle id and must be rejected.
    for bundle_path in bundle_paths:
        if not bundle_path:
            errors.append(
                PlanLiftError(
                    f"profile {profile_name}: empty bundle path; "
                    f"every entry in ``bundles`` must be a non-empty "
                    f"path to a bundle file",
                    plan_id=profile_name,
                )
            )
            continue
        path = Path(bundle_path)
        # ``Path.stem`` is empty only when the path has no
        # filename component at all (e.g. ``"bundles/"`` after
        # normalization keeps ``name == "bundles"``); ``bundles/.yaml``
        # keeps ``stem == ".yaml"`` because Path treats leading-dot
        # names as hidden files. Both shapes — a literal trailing
        # separator in the source string, an empty ``Path.stem``,
        # or a leading-dot ``Path.name`` — are degenerate bundle
        # ids and must be rejected.
        if (
            bundle_path.endswith("/")
            or bundle_path.endswith("\\")
            or path.stem == ""
            or path.name.startswith(".")
        ):
            errors.append(
                PlanLiftError(
                    f"profile {profile_name}: bundle path {bundle_path!r} "
                    f"has empty id; the path must resolve to a non-empty "
                    f"stem (filename without extension)",
                    plan_id=profile_name,
                )
            )

    # 3. Reserved bundle id patterns — collisions with Python /
    #    pytest internals and underscore-prefixed stems (a
    #    Python-private convention that should not leak into
    #    user-facing bundle ids).
    for bundle_path in bundle_paths:
        if not bundle_path:
            continue
        stem = Path(bundle_path).stem
        if not stem:
            continue
        if stem.startswith("_") or stem in _RESERVED_BUNDLE_IDS:
            errors.append(
                PlanLiftError(
                    f"profile {profile_name}: bundle {stem!r} uses "
                    f"reserved or underscore-prefix id; reserved ids "
                    f"collide with python/pytest internals "
                    f"({sorted(_RESERVED_BUNDLE_IDS)!r}, or any id "
                    f"starting with '_')",
                    plan_id=profile_name,
                )
            )

    return errors


__all__ = ["check_profile_topology"]
