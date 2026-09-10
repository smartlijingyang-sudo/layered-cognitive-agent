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
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Protocol, TypeVar, runtime_checkable

from cordis import Context  # noqa: TC002
from pydantic import BaseModel, ConfigDict

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision, Observation, Reflection


class PhaseOutput(BaseModel):
    """Typed snapshot of one subgraph's terminal contribution.

    Frozen Pydantic + ``extra="forbid"`` keeps the surface stable
    (ADR-0195 §1.4 D1-D4). At most one of each field is non-None per
    run; ``Decision`` is the canonical ``act.advance`` payload.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: Decision | None = None
    observation: Observation | None = None
    reflection: Reflection | None = None
    response: LLMResponse | None = None


class ChannelNotSatisfiedError(LookupError):
    """Raised when ``read(want=T)`` cannot find a producer for type ``T``."""


T = TypeVar("T")


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

    def __init__(self, *, ctx: Context) -> None:
        self._ctx = ctx
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
        self._ctx.emit("subgraph.phase_output", producer_node, phase, output)

    def read(self, *, consumer_node: str, want: type[T]) -> T:
        field_name = getattr(want, "__name__", None)
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
        merged = PhaseOutput(
            decision=delta.decision if delta.decision is not None else self._last("decision"),
            observation=delta.observation
            if delta.observation is not None
            else self._last("observation"),
            reflection=delta.reflection
            if delta.reflection is not None
            else self._last("reflection"),
            response=delta.response if delta.response is not None else self._last("response"),
        )
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
