"""SessionActivation — plan-bound runtime closure handle.

Per ADR-0199 §2.2.2, ``SessionActivation`` is the canonical SSOT for a
running closure: it carries the activation hash plus the immutable triple
``(plan_ref, graph_ref, plugin_set_ref)`` plus session identity and the
trust envelope inherited from the originating profile/bundle.

Invariant I-HPC-3 (Activation 绑定): every durable run event must carry
``activation_ref`` (or the equivalent ``plan_ref``/``graph_ref``/
``plugin_set_ref`` triple). Doctor, replay, and failure attribution all
locate closures through this handle.

Pure contracts-layer dataclass. No I/O, no resolve, no compile, no boot.
``CompiledRunPlan`` and ``TrustEnvelope`` are referenced via
``TYPE_CHECKING`` because the parallel PRs P1-01 / P1-02 land alongside;
``from __future__ import annotations`` keeps those references string-only
at runtime so this module imports in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lca.contracts.protocols.state.plan import CompiledRunPlan
    from lca.contracts.runtime.trust import TrustEnvelope


@dataclass(frozen=True, slots=True)
class SessionActivation:
    """Plan-bound runtime closure handle.

    Attributes:
        activation_ref: Opaque hash binding ``(plan_ref, graph_ref,
            plugin_set_ref, session_id)``. Produced by
            ``harness.runtime.activation_ref.compute_activation_ref``.
        plan_ref: Stable identifier of the ``CompiledRunPlan``.
        graph_ref: Stable identifier of the resolved phase graph.
        plugin_set_ref: Stable identifier of the resolved plugin set.
        profile_path: Absolute path of the profile that produced the plan.
        session_id: Unique identifier for this run-time closure.
        trust_envelope: Provenance + granted privileges inherited from the
            originating profile/bundle (ADR-0199 §3.4).
        compiled_plan: Optional read-only reference to the resolved plan;
            kept for callers that need the full plan without re-compiling.
    """

    activation_ref: str
    plan_ref: str
    graph_ref: str
    plugin_set_ref: str
    profile_path: str
    session_id: str
    trust_envelope: TrustEnvelope
    compiled_plan: CompiledRunPlan | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "activation_ref",
            "plan_ref",
            "graph_ref",
            "plugin_set_ref",
            "profile_path",
            "session_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"SessionActivation.{field_name} must be a non-empty string")


__all__ = ("SessionActivation",)
