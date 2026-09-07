"""Privilege projection from declarative plugin spec → PluginContract (ADR-0199 P3-02).

Per ADR-0199 §3.1, ``privileges`` is the fourth dimension orthogonal to
``provides``/``requires``/``resources``: it lists the side-effects a plugin
is **authorised** to perform (e.g. ``journal.append``, ``network.egress``),
distinct from the capabilities it **exposes**.

Per I-HPC-5, an undeclared privilege triggers fail-closed at setup time
(enforced in :class:`lca.contracts.harness.composition.plugin_contract.PluginContract`
and downstream in the guard stack). This module is the **pure-data
normalisation seam** that lives between the YAML / decorator declaration and
the canonical :class:`PluginContract.privileges` tuple.

This module:
  - Reads ``meta["privileges"]`` from the declaration mapping (list[str])
  - Validates the shape (sequence of non-empty strings)
  - Dedupes while preserving insertion order (deterministic, C8)
  - Returns a frozen ``tuple[str, ...]`` suitable for ``PluginContract``

Per I-HPC-5 the unknown-prefix gate is **not** enforced here — that lives in
``PluginContract.__post_init__`` so the projector stays purely
declarative and forward-compatible (new prefixes can be added in later
PRs without rewriting this helper).

COMPAT(owner: ADR-0199 P3-02, from: meta.privileges as raw ``list[str]``,
       to: ``PluginContract.privileges`` tuple; delete_when: declarative
       profile YAML projection wired into the resolver pipeline; current
       integration lives in :mod:`lca.harness.plugin.declaration`)
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class PrivilegeProjectionError(ValueError):
    """Raised when ``meta["privileges"]`` has an invalid shape.

    Per ADR-0199 P3-02: missing key, wrong container type, non-string
    element, or empty-string entry all fail this seam. Unknown prefixes
    are **not** an error here — they emit a warning in
    :meth:`PluginContract.__post_init__` (P3-01) so the closed-set can
    be widened later without rewriting callers.
    """


def project_privileges(meta: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Project ``meta["privileges"]`` into a deterministic tuple.

    Per ADR-0199 P3-02:

    - ``None`` or missing key → ``()`` (backward-compatible default)
    - Non-``list``/``tuple`` container → :class:`PrivilegeProjectionError`
    - Non-``str`` element → :class:`PrivilegeProjectionError`
    - Empty-string element → :class:`PrivilegeProjectionError`
    - Duplicates collapse, **insertion order preserved** (C8 deterministic)

    Per I-HPC-5, unknown privilege prefixes are NOT rejected here; the
    projector stays purely declarative. The closed-set gate lives in
    :class:`PluginContract.__post_init__` so adding a new prefix is a
    one-line, forward-compatible change.
    """
    if meta is None:
        return ()

    raw = meta.get("privileges")
    if raw is None:
        return ()

    if not isinstance(raw, (list, tuple)):
        raise PrivilegeProjectionError(
            f"meta.privileges must be a list or tuple, got {type(raw).__name__}"
        )

    out: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, str):
            raise PrivilegeProjectionError(
                f"meta.privileges[{index}] must be a string, got {type(item).__name__}"
            )
        if not item:
            raise PrivilegeProjectionError(f"meta.privileges[{index}] must be non-empty")
        if item not in seen:
            out.append(item)
            seen.add(item)

    return tuple(out)


__all__ = ("PrivilegeProjectionError", "project_privileges")
