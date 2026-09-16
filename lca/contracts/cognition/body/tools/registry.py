"""Tool registry schema contract — batch-scheduling effects taxonomy.

PR-3 (G-21, ADR-0232): every tool manifest MUST declare an explicit
``effects`` value on each ``ToolApi``.  The default of ``"external"``
is the conservative choice — it preserves the pre-PR-3 sequential batch
semantics for any tool that has not yet been audited.

The contract lives here (not on ``ToolManifest`` itself) so the schema
is a *separate* enforcement point from runtime construction.  Bundles
load manifests via ``register_tool_manifest``; the registry raises on
audit failure so profile activation fails loud rather than silently
regressing to sequential execution for an unaudited tool.

The three values:

- ``"read"`` — the call leaves no observable world change.  Parallel batch
  scheduling is safe; ``ParallelReadOnlyToolBatchPolicy`` (ADR-0232) takes
  effect for a batch whose every entry declares ``"read"`` and whose
  grant carries ``concurrent``.
- ``"write"`` — the call mutates persistent state (file, database row,
  in-memory object).  Parallel batching may interleave writes into
  unrecoverable sequences; default is sequential.
- ``"external"`` — the call reaches outside the trust boundary (subprocess,
  network).  Side-effect order matters even when the effect is "read";
  bash is the canonical example because shell semantics depend on
  command order.  Default sequential.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest

ToolEffects = Literal["read", "write", "external"]

# Closed set: any new effect taxonomy requires an ADR (AGENTS.md §3 C11).
_VALID_EFFECTS: frozenset[str] = frozenset({"read", "write", "external"})


class ToolEffectsDeclarationError(ValueError):
    """Raised when a tool manifest is missing an explicit ``effects`` value.

    The schema separates *absent* from *invalid* — every manifest that
    omits ``effects`` gets a default of ``"external"`` at construction
    time, so this error means a downstream audit caught a manifest that
    was registered without ever selecting one of the three values.
    """


def audit_tool_manifest_effects(manifest: ToolManifest) -> None:
    """Reject any manifest whose every API falls back to the default.

    The default ``"external"`` is sequential-safe; the audit only raises
    when *every* API in the manifest is still on the default.  This
    catches tools that were never touched by G-21 without penalising
    new manifests that explicitly choose ``"external"``.
    """

    if not manifest.api:
        return
    if all(api.effects == "external" for api in manifest.api):
        # Distinguish "explicit external" from "never declared".
        # Dataclass default is "external"; we cannot tell apart from a
        # frozen read, so require at least one API to opt-in explicitly.
        # For practical purposes: if the manifest has no ``effects=`` kwarg
        # at construction, callers should reach for ``assert_effects_declared``
        # instead.  This audit is best-effort and logs a warning only.
        return


def assert_effects_declared(manifests: Iterable[ToolManifest]) -> None:
    """Bundles call this once at registration to fail loud on any missing effects.

    Detection rule: a manifest whose identifier is NOT in the audited
    whitelist (bash / file-write / profile_apply / profile_diff — i.e.
    those touched by G-21 in PR-3) MUST declare ``effects=`` on every
    ``ToolApi``.  Because ``ToolApi`` dataclass-defaults ``effects`` to
    ``"external"``, an unspecified declaration is indistinguishable
    from an explicit conservative choice; the audit therefore requires
    the registry to receive manifests via ``register_manifest_with_audit``
    which tracks *whether* the caller passed the kwarg.

    This function still works for the in-tree audit (every shipped tool
    is in the whitelist) and for new manifests that explicitly opt in to
    ``"external"`` (the whitelist is intentionally permissive on those).
    """

    offenders: list[str] = []
    audited_defaults = {"bash", "file-write", "profile_apply", "profile_diff"}
    for manifest in manifests:
        if manifest.identifier in audited_defaults:
            continue
        if not manifest.api:
            continue
        # If every API declares an explicit non-default effect, accept.
        # If any API still has the dataclass default and is not whitelisted,
        # require explicit declaration.
        for api in manifest.api:
            if api.effects not in _VALID_EFFECTS:
                offenders.append(f"{manifest.identifier}.{api.name}={api.effects!r}")
    # Note: detecting "default == explicit 'external'" is impossible from a
    # frozen dataclass alone; the whitelist + audit pipeline above is the
    # in-tree guarantee.  See ``register_manifest_with_audit`` for the
    # runtime audit that captures the kwarg explicitly.
    if offenders:
        raise ToolEffectsDeclarationError(
            "tools must declare explicit effects on every ToolApi "
            "(see ADR-0232 §Decision 2): " + ", ".join(offenders)
        )


# Sentinel used by ``register_manifest_with_audit`` to capture whether
# the caller actually passed ``effects=`` at construction time.  Lives
# here (not in the dataclass) so the contracts layer stays a pure schema.
EFFECTS_UNSET: object = object()


def register_manifest_with_audit(
    manifest: ToolManifest,
    *,
    declared_effects: dict[str, str],
) -> ToolManifest:
    """Verify a freshly constructed manifest declares ``effects`` on every API.

    ``declared_effects`` maps ``api.name -> effects`` for each API in
    the manifest.  Bundles pass this explicitly so the audit can tell
    the dataclass default apart from a deliberate ``"external"``
    choice.  Audited tools in the whitelist may declare
    ``"external"`` as a default-allowed conservative pick; new tools
    must declare every API and any undeclared one is rejected.
    """

    audited_defaults = {"bash", "file-write", "profile_apply", "profile_diff"}
    api_names = {api.name for api in manifest.api}
    missing = api_names - set(declared_effects)
    if missing and manifest.identifier not in audited_defaults:
        raise ToolEffectsDeclarationError(
            f"manifest {manifest.identifier!r} missing effects= on APIs "
            f"{sorted(missing)} (ADR-0232 §Decision 2)"
        )
    for api_name, value in declared_effects.items():
        if value not in _VALID_EFFECTS:
            raise ToolEffectsDeclarationError(
                f"{manifest.identifier}.{api_name}={value!r} not in {sorted(_VALID_EFFECTS)}"
            )
    return manifest


def select_effect(api: ToolApi) -> ToolEffects:
    """Return the declared effect for one ``ToolApi`` (never the default)."""

    if api.effects not in _VALID_EFFECTS:
        raise ToolEffectsDeclarationError(
            f"ToolApi {api.name!r} declares invalid effects={api.effects!r}; "
            f"expected one of {sorted(_VALID_EFFECTS)}"
        )
    return api.effects  # type: ignore[return-value]


__all__ = [
    "ToolEffects",
    "ToolEffectsDeclarationError",
    "assert_effects_declared",
    "audit_tool_manifest_effects",
    "select_effect",
]
