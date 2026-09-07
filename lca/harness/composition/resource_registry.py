"""Resource compile projection (ADR-0199 §3.1 / P4-02).

Per ADR-0199 §3.1, ``resources`` is the 4th plugin dimension (read-only,
distributable content). Per I-HPC-6, resource content is read-only and
never gains execute permission.

This module is the compile-time projector:

    meta.resources: list[dict]  →  tuple[ResourceId, ...]

The projection:
  - Validates each entry's shape (kind/namespace/name or ref string)
  - Deduplicates by canonical ref
  - Returns a sorted, frozen tuple suitable for storage in
    ``PluginContract.resources`` (added in a future PR) or directly in
    the compiled plan

The :class:`ResourceRegistry` itself is a thin wrapper that maps
ResourceId → provider name; runtime lookup goes through the existing
SkillProvider / prompt / role providers via their respective seams
(the registry only holds the SSOT mapping for diagnostics and tooling).

This module is intentionally pure: no I/O, no env reads, no logging
(C8 determinism).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from lca.contracts.runtime.resource import ResourceId


class ResourceProjectionError(ValueError):
    """Raised when ``meta.resources`` has an invalid shape."""


def project_resources(
    meta: Mapping[str, Any] | None,
) -> tuple[ResourceId, ...]:
    """Project ``meta["resources"]`` → ``tuple[ResourceId, ...]``.

    Per ADR-0199 §3.1 + P4-02, this is the compile-time seam between the
    declarative plugin spec (``meta.resources`` list of dicts / strings
    / ``ResourceId`` instances) and the canonical ``tuple[ResourceId, ...]``
    that downstream code stores in ``PluginContract.resources``.

    Args:
      meta: a Mapping with key ``"resources"`` whose value is a list/tuple
            of dicts (``{"kind", "namespace", "name"}``), pre-formed
            ``"<kind>:<namespace>/<name>"`` strings, or :class:`ResourceId`
            instances.

    Returns:
      Sorted (by ``to_ref()``), deduplicated tuple of ``ResourceId``.

    Raises:
      :class:`ResourceProjectionError` on invalid container shape,
      missing dict keys, unknown kind, reserved namespace, invalid
      name/namespace pattern, or unparseable string ref.

    Per C8: deterministic; identical input → identical output (sorted).
    Per I-HPC-6: content is read-only; this projector does NOT register
    executable capabilities.
    """
    if meta is None:
        return ()

    raw = meta.get("resources")
    if raw is None:
        return ()

    if not isinstance(raw, (list, tuple)):
        raise ResourceProjectionError(
            f"meta.resources must be a list or tuple, got {type(raw).__name__}"
        )

    out: list[ResourceId] = []
    seen_refs: set[str] = set()

    for i, item in enumerate(raw):
        if isinstance(item, ResourceId):
            rid = item
        elif isinstance(item, str):
            try:
                rid = ResourceId.from_ref(item)
            except ValueError as exc:
                raise ResourceProjectionError(
                    f"meta.resources[{i}] string ref is invalid: {exc}"
                ) from exc
        elif isinstance(item, Mapping):
            try:
                rid = ResourceId(
                    kind=item["kind"],
                    namespace=item["namespace"],
                    name=item["name"],
                )
            except KeyError as exc:
                raise ResourceProjectionError(
                    f"meta.resources[{i}] missing key {exc.args[0]!r}; "
                    f"expected keys: kind, namespace, name"
                ) from exc
            except ValueError as exc:
                raise ResourceProjectionError(
                    f"meta.resources[{i}] dict is invalid: {exc}"
                ) from exc
        else:
            raise ResourceProjectionError(
                f"meta.resources[{i}] must be a string, dict, or ResourceId; "
                f"got {type(item).__name__}"
            )

        ref = rid.to_ref()
        if ref not in seen_refs:
            out.append(rid)
            seen_refs.add(ref)

    # Sort for determinism (C8)
    out.sort(key=lambda r: r.to_ref())
    return tuple(out)


class ResourceRegistry:
    """Read-only registry that maps ResourceId → provider name (ADR-0199 P4-02).

    The registry is populated at compile time from the union of all
    plugin contracts' resources. At runtime, lookup goes through the
    existing SkillProvider / prompt / role providers via their
    respective seams; the registry only holds the SSOT mapping for
    diagnostics and tooling.

    Per I-HPC-6: this registry does NOT grant execute permission; it
    is a name-to-provider map, not an authority token.
    """

    def __init__(self, resources: Sequence[ResourceId] = ()) -> None:
        self._by_ref: dict[str, ResourceId] = {}
        for rid in resources:
            self._by_ref[rid.to_ref()] = rid

    @property
    def resources(self) -> tuple[ResourceId, ...]:
        """Sorted, deduplicated tuple of registered resources."""
        return tuple(sorted(self._by_ref.values(), key=lambda r: r.to_ref()))

    def __len__(self) -> int:
        return len(self._by_ref)

    def __contains__(self, rid: object) -> bool:
        if isinstance(rid, ResourceId):
            return rid.to_ref() in self._by_ref
        if isinstance(rid, str):
            return rid in self._by_ref
        return False

    def get(self, rid: ResourceId | str) -> ResourceId | None:
        """Look up a resource by ResourceId or canonical ref string."""
        if isinstance(rid, ResourceId):
            return self._by_ref.get(rid.to_ref())
        return self._by_ref.get(rid)

    def add(self, rid: ResourceId) -> None:
        """Add a resource to the registry (idempotent on duplicate ref)."""
        self._by_ref[rid.to_ref()] = rid

    def merge(self, other: ResourceRegistry) -> ResourceRegistry:
        """Return a new registry that contains the union of this and other.

        On duplicate refs, the caller's entry wins (deterministic; does
        not raise). Neither input is mutated.
        """
        merged = dict(self._by_ref)
        merged.update(other._by_ref)
        out = ResourceRegistry()
        out._by_ref = merged
        return out


__all__ = (
    "ResourceProjectionError",
    "ResourceRegistry",
    "project_resources",
)
