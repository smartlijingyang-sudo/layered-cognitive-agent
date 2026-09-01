"""``spine.reflector.context`` plugin — D11 context auto-source.

Per ADR-0165.1 §7.5.3, this plugin contributes a
:class:`FieldProducer` that injects budget, precondition,
circuit-breaker state, post-state delta, and side-effect fields
into spine ``EventRecord`` payloads. The producer is the
"context" axis of the four-axis auto-source scheme (signature /
context / runtime / manifest) — the spine's ``EmitPipeline``
calls :meth:`ContextFieldProducer.produce` once per phase and
merges the returned dict alongside other producers, sorted by
``priority``.

Wiring
------
Profile boot calls ``ctx.provide("field_producer.context",
ContextFieldProducer())`` from :func:`setup`; downstream code
(``wrap_instrument`` in a later PR) fetches it via
``ctx.require("field_producer.context")`` and registers it with
the run's :class:`EmitPipeline`. Until that wiring lands, the
producer is safe to instantiate and exercise in isolation —
``produce`` returns well-formed placeholder payloads.

Real values for ``budget_at_entry`` are pulled from
:class:`lca.infrastructure.observability.spine.context.SpineContext`
when present; ``preconditions``, ``circuit_breaker_state``,
``post_state_delta``, ``budget_consumed``, and
``side_effects_added`` are populated by the runtime wrappers in
follow-up work and default to conservative placeholders here.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.spine.producer import Phase
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class ContextFieldProducer:
    """Auto-source for context/budget/circuit-breaker fields (D11).

    The producer follows the convention used by every other spine
    ``FieldProducer`` (ADR-0165.1 §D12) and is merged into the
    ``EventRecord.payload`` by ``EmitPipeline`` in ascending
    ``priority`` order. Lower-priority writers win on key
    conflict, which lets the spantree (priority 5) stamp span
    identifiers before higher-numbered producers add business
    fields.
    """

    name: str = "spine.reflector.context"
    priority: int = 20
    enabled: bool = True

    def produce(
        self,
        *,
        fn: Any,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        ctx: Any,
        span: Any,
        phase: Phase,
    ) -> dict[str, Any]:
        """Return the context/budget/breaker fields for ``phase``.

        ``phase`` follows the standard ``"pre" | "post" | "exception"``
        vocabulary defined by ``FieldProducer``. Phases outside
        ``"pre"`` and ``"post"`` contribute no fields (the
        exception-phase envelope is owned by the classifier
        producers — see ADR-0165.1 §7.5.2/4).
        """
        if phase == "pre":
            return self._produce_pre(ctx=ctx)
        if phase == "post":
            return self._produce_post(ctx=ctx)
        return {}

    # ── phase helpers ────────────────────────────────────────────────

    @staticmethod
    def _produce_pre(*, ctx: Any) -> dict[str, Any]:
        """Build the ``pre``-phase payload.

        ``budget_at_entry`` reads from
        :class:`lca.infrastructure.observability.spine.context.SpineContext`
        when ``ctx`` exposes ``budget_snapshot()``; otherwise an empty
        dict is returned so downstream consumers always observe a
        well-formed mapping.
        """
        return {
            "preconditions": "captured_at_phase=pre",
            "budget_at_entry": _budget_snapshot(ctx),
        }

    @staticmethod
    def _produce_post(*, ctx: Any) -> dict[str, Any]:
        """Build the ``post``-phase payload.

        ``post_state_delta`` / ``budget_consumed`` /
        ``side_effects_added`` are populated by ``wrap_instrument``
        in a follow-up PR; the placeholders below keep the seam
        shape stable until then. ``circuit_breaker_state`` defaults
        to ``"closed"`` to mirror the canonical "no breaker tripped"
        posture at the boundary.
        """
        return {
            "post_state_delta": {},
            "budget_consumed": {},
            "circuit_breaker_state": "closed",
            "side_effects_added": (),
        }


def _budget_snapshot(ctx: Any) -> dict[str, Any]:
    """Return a budget snapshot from ``ctx`` when available.

    The context layer (later PR) attaches a ``budget_snapshot()``
    callable to the runtime ``ctx``. Until then, treat any object
    that doesn't expose that method as "no budget context wired"
    and return an empty dict.
    """
    snapshot = getattr(ctx, "budget_snapshot", None)
    if not callable(snapshot):
        return {}
    result = snapshot()
    return result if isinstance(result, dict) else {}


@plugin(
    id="spine.reflector.context",
    provides=("field_producer.context",),
    requires=(),
    layer="L0",
    kind=PluginKind.SEAM,
    effects="none",
    description=(
        "auto-source (D11 context axis): injects preconditions / budget_at_entry "
        "/ post_state_delta / budget_consumed / circuit_breaker_state / "
        "side_effects_added into EventRecord.payload via EmitPipeline merge."
    ),
    test_suite="tests.lca_plugins.observability.spine.test_reflector_context",
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Install the producer under the ``field_producer.context`` seam."""
    ctx.provide("field_producer.context", ContextFieldProducer())


__all__ = ["ContextFieldProducer", "setup"]
