"""PhaseOutputChannel — typed bus for subgraph node-to-node results.

Per plan §3.4: a per-run bus that holds the typed outputs the subgraph
framework cares about (``Decision`` / ``Observation`` / ``Reflection`` /
``LLMResponse``). Backed by two sinks:

- **typed dict (primary)**: ``O(1)`` lookup, ``read(want=T)`` returns
  the typed instance or raises ``ChannelNotSatisfiedError``;
- **Cordis ``ctx.emit`` broadcast (secondary)**: any plugin can listen
  to ``subgraph.phase_output`` for observability / debugging / external
  hooks. This sink is intentionally not the source of truth — it cannot
  express type-based routing or fail-loud on a missing producer.

The Channel is intentionally *per-run*; one channel instance is owned by
the subgraph runner for the lifetime of a single ``driver.run()``.

ADR-0195 §1.4 (information lineage): every field on :class:`PhaseOutput`
has a static definition point (this module), constraint
(``ConfigDict(frozen=True, extra="forbid")``), no transformation chain
across boundaries, and explicit consumers (drivers, absorbers,
subgraph runner).

ADR-0219 §10.11.5: the close-out field set is owned by
:class:`lca.cognition.close_out.CLOSE_OUT_FIELDS`. ``PhaseOutput`` builds
its dynamic field set from that tuple plus two terminal-run metadata
fields (``outcome_kind`` / ``error``) that are not part of the
close-out surface but live on the same model so the runner can return
success and failure through one typed envelope.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Protocol, TypeVar, runtime_checkable

from cordis import Context  # noqa: TC002
from pydantic import BaseModel, ConfigDict, create_model

from lca.cognition.close_out import close_out_types
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)


def _build_phase_output() -> type[BaseModel]:
    """Build :class:`PhaseOutput` from ``CLOSE_OUT_FIELDS`` + terminal-run metadata.

    Keeps the field set in lock-step with the close-out SSOT in
    :mod:`lca.cognition.close_out`; an entry added there appears here
    automatically. Terminal-run metadata (``outcome_kind`` /
    ``error``) are not part of the close-out surface but share the
    model so the runner returns one typed envelope.

    ``__config__`` is passed at construction time because
    ``create_model`` only honours ``model_config`` declared during
    model creation — assigning it afterwards is silently ignored by
    Pydantic v2.
    """
    fields: dict[str, Any] = {
        name: (payload_type | None, None) for name, payload_type in close_out_types().items()
    }
    fields["outcome_kind"] = (ExecutionOutcome | None, None)
    fields["error"] = (str | None, None)
    return create_model(
        "PhaseOutput",
        __base__=BaseModel,
        __config__=ConfigDict(frozen=True, extra="forbid"),
        **fields,
    )


PhaseOutput: type[BaseModel] = _build_phase_output()
"""Typed snapshot of one subgraph's terminal contribution.

Frozen Pydantic + ``extra="forbid"`` keeps the surface stable
(ADR-0195 §1.4 D1-D4). At most one of each close-out field is non-None
per run; ``Decision`` is the canonical ``act.advance`` payload.

The four close-out fields (``decision`` / ``observation`` /
``reflection`` / ``response``) are derived from
``lca.cognition.close_out.CLOSE_OUT_FIELDS``; the two terminal-run
metadata fields (``outcome_kind`` / ``error``) are static.

ADR-0219 §10.11 item (3): ``outcome_kind`` + ``error`` carry the
failure shape that ``SubgraphRunner.run`` would otherwise discard at
its return site. Both default to ``None`` on the success path; the
runner populates them only when the inner driver returned a
``DeclarativeRunOutcome(kind=FAILED)``. Terminal-run metadata —
``absorb()`` deliberately does NOT copy these into the merged
snapshot, since success/failure is not a mergeable payload.
"""

# Ensure the dynamic model exposes the field set we expect at import
# time. If this fails, the close-out SSOT and the model drifted.
from lca.cognition.close_out import CLOSE_OUT_FIELDS as _COF  # noqa: E402

if not set(_COF).issubset(set(PhaseOutput.model_fields.keys())):
    raise RuntimeError(
        "PhaseOutput field set drifted from CLOSE_OUT_FIELDS SSOT; "
        "check lca.cognition.close_out.CLOSE_OUT_FIELDS"
    )


class ChannelNotSatisfiedError(LookupError):
    """Raised when ``read(want=T)`` cannot find a producer for type ``T``."""


T = TypeVar("T")


def _reverse_close_out_field(want: type[Any]) -> str | None:
    """Map a typed payload class back to its close-out field name.

    Returns ``None`` for types that are not part of
    :data:`lca.cognition.close_out.CLOSE_OUT_FIELDS`; callers treat
    ``None`` as a miss and surface ``ChannelNotSatisfiedError``.
    """
    from lca.cognition.close_out import close_out_types

    for name, payload_type in close_out_types().items():
        if payload_type is want:
            return name
    return None


@runtime_checkable
class PhaseOutputChannel(Protocol):
    """Surface area exposed to drivers / runners / outer interpreters.

    Implementations must be safe to call from a single asyncio task
    without external locking (subgraph driver is single-threaded per
    run).
    """

    def publish(
        self,
        *,
        producer_node: str,
        phase: str,
        output: PhaseOutput,
    ) -> None: ...

    def read(self, *, consumer_node: str, want: type[T]) -> T: ...

    def absorb(self, delta: PhaseOutput) -> None: ...

    def snapshot(self) -> Mapping[str, PhaseOutput]: ...


class InMemoryPhaseOutputChannel:
    """Per-run, in-process implementation of :class:`PhaseOutputChannel`.

    Owns two sinks:

    - ``self._outputs``: dict keyed by ``"{phase}::{producer_node}"`` —
      primary typed lookup path. ``read(want=T)`` walks values and
      returns the first non-None field of the requested type. Raises
      :class:`ChannelNotSatisfiedError` if no producer satisfied the
      request — fail-loud per plan §3.4.
    - ``self._ctx.emit(...)``: Cordis broadcast for observability. Two
      event names:

      - ``subgraph.phase_output`` — fired by ``publish`` for each
        producer write;
      - ``subgraph.phase_output.absorbed`` — fired by ``absorb`` with
        the merged snapshot.

    Both sinks are written on every ``publish``; ``absorb`` only emits
    (no typed-dict write) to avoid double-storing the merged snapshot.

    Why a dedicated channel rather than re-using ``ctx.emit`` alone:

    - ``ctx.emit`` is a broadcast: there is no type-based routing;
    - subscribers cannot declare ``want=Decision`` and get fail-loud
      on miss;
    - emissions are container-global, with no per-run isolation;
    - we still want broadcast for observability — hence the dual sink.
    """

    def __init__(self, *, ctx: Context | None = None) -> None:
        self._ctx = ctx
        # ctx=None:no-op broadcast (typed dict 仍工作,emit 静默跳过)
        self._outputs: dict[str, PhaseOutput] = {}

    def publish(
        self,
        *,
        producer_node: str,
        phase: str,
        output: PhaseOutput,
    ) -> None:
        key = f"{phase}::{producer_node}"
        self._outputs[key] = output
        if self._ctx is not None:
            self._ctx.emit("subgraph.phase_output", producer_node, phase, output)

    def read(self, *, consumer_node: str, want: type[T]) -> T:
        # ADR-0219 §10.11.5: type → field name is owned by the
        # cognition close-out SSOT (one entry per ``CLOSE_OUT_FIELDS``).
        # Reverse-lookup avoids re-listing the field names here.
        field_name = _reverse_close_out_field(want)
        for output in self._outputs.values():
            value = getattr(output, field_name, None) if field_name else None
            if value is not None:
                return value  # type: ignore[no-any-return]
        raise ChannelNotSatisfiedError(
            f"consumer_node={consumer_node!r} wants {field_name!r}, "
            f"but no producer emitted that. "
            f"published: {sorted(self._outputs.keys())}"
        )

    def absorb(self, delta: PhaseOutput) -> None:
        # ADR-0219 §10.11.5: walk ``CLOSE_OUT_FIELDS`` instead of
        # listing the four field names here. Each field falls back to
        # the most recently published non-None value (``last-write-wins``
        # within a single inner subgraph).
        from lca.cognition.close_out import CLOSE_OUT_FIELDS

        kwargs: dict[str, Any] = {}
        for field_name in CLOSE_OUT_FIELDS:
            value = getattr(delta, field_name, None)
            if value is None:
                value = self._last(field_name)
            kwargs[field_name] = value
        merged = PhaseOutput(**kwargs)
        if self._ctx is not None:
            self._ctx.emit("subgraph.phase_output.absorbed", merged)

    def snapshot(self) -> Mapping[str, PhaseOutput]:
        return MappingProxyType(dict(self._outputs))

    def _last(self, field_name: str) -> Any:
        """Return the most recently published non-None value for ``field_name``."""
        last_value: Any = None
        for output in self._outputs.values():
            candidate = getattr(output, field_name, None)
            if candidate is not None:
                last_value = candidate
        return last_value


__all__ = [
    "ChannelNotSatisfiedError",
    "InMemoryPhaseOutputChannel",
    "PhaseOutput",
    "PhaseOutputChannel",
]
