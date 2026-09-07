"""EffectPolicyPlan privilege projection (ADR-0199 §3.1 / P3-06, I-HPC-5).

Per ADR-0199 §3.1, ``privileges`` is the fourth dimension orthogonal to
``provides``/``requires``/``resources``: it lists the side-effects a plugin
is **authorised** to perform (e.g. ``journal.append``,
``network.egress``), distinct from the capabilities it exposes.

Per I-HPC-5, an undeclared privilege triggers fail-closed at setup time.
This module is the **pure-data normalisation seam** between the
declarative compilation pipeline (PluginSpec → ``compile_effect_policy``)
and the Body path enforcement (which reads ``EffectPolicyPlan.privileges``
to decide whether a runtime effect is in scope).

This module wraps :func:`compile_effect_policy` with an extra step that
merges :attr:`PluginContract.privileges` into the resulting
``EffectPolicyPlan``. The merge is additive and deterministic (sorted +
deduped, C8). The wrapper does NOT modify the existing
``compile_effect_policy`` signature; it is opt-in so the migration window
keeps the prior shape.

Per ADR-0015 contracts purity, this module only reads from typed dataclass
fields (``PluginContract.privileges``) and ``EffectPolicyPlan``; no I/O,
no environment access, no logger.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.contracts.harness.composition.plugin_contract import PluginContract
    from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
        EffectPolicyPlan,
    )
    from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
        PluginSpec,
    )


def project_privileges_into_effect_policy(
    plan: "EffectPolicyPlan",  # noqa: UP037 — forward reference (TYPE_CHECKING)
    plugin_contracts: tuple["PluginContract", ...] = (),  # noqa: UP037 — forward reference
) -> "EffectPolicyPlan":  # noqa: UP037 — forward reference
    """Augment an existing ``EffectPolicyPlan`` with privilege projections.

    Reads :attr:`PluginContract.privileges` for each contract and unions
    them with any pre-existing ``plan.privileges`` into a sorted,
    deduplicated tuple assigned to ``plan.privileges``. The function does
    NOT mutate the input plan — it returns the same plan when the new
    privileges are empty, or a ``dataclasses.replace`` copy otherwise.

    Per C8 deterministic: the resulting tuple is sorted + deduped.
    Per I-HPC-5: union of all declared privileges; the Body path fails
    closed at setup if a plugin attempts a privilege outside this set
    and not granted by the active ``TrustEnvelope``.
    """
    # Collect from contracts (set semantics: dedup across contracts)
    collected: set[str] = set()
    for contract in plugin_contracts:
        # ``PluginContract.privileges`` is already validated as
        # tuple[str, ...] with non-empty strings; defensive coercion for
        # callers that may pass ad-hoc dataclass-like objects.
        for priv in getattr(contract, "privileges", ()) or ():
            collected.add(priv)

    # Union with any pre-existing privileges (idempotent)
    existing = set(getattr(plan, "privileges", ()) or ())
    merged = existing | collected

    new_privileges = tuple(sorted(merged))

    # Fast path: nothing to change → preserve identity (and frozen state).
    existing_tuple = tuple(getattr(plan, "privileges", ()) or ())
    if new_privileges == existing_tuple:
        return plan

    return dataclasses.replace(plan, privileges=new_privileges)


def build_effect_policy_with_privileges(
    specs: tuple["PluginSpec", ...],  # noqa: UP037 — forward reference (TYPE_CHECKING)
    plugin_contracts: tuple["PluginContract", ...] = (),  # noqa: UP037 — forward reference
) -> "EffectPolicyPlan":  # noqa: UP037 — forward reference
    """Compile ``EffectPolicyPlan`` from ``PluginSpec`` declarations AND project privileges.

    Convenience wrapper that calls :func:`compile_effect_policy` and then
    :func:`project_privileges_into_effect_policy`. ``compile_effect_policy``
    remains the authoritative builder for the gateway / allowed / approval /
    idempotency surface; this wrapper only adds the ``privileges`` field.

    Per ADR-0199 §3.1 + I-HPC-5: the union of privileges is what the Body
    path enforces; callers using this wrapper get a plan ready for I-HPC-5
    enforcement without an extra scan over plugin contracts.
    """
    # Local import to avoid an import cycle at module load: the
    # ``policy`` module already imports ``EffectPolicyPlan`` from contracts.
    from lca.harness.declarative.compile.effect.policy import (
        compile_effect_policy,
    )

    plan = compile_effect_policy(specs)
    return project_privileges_into_effect_policy(plan, plugin_contracts)


__all__ = (
    "build_effect_policy_with_privileges",
    "project_privileges_into_effect_policy",
)
