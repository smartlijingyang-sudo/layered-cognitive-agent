"""FieldProducer Protocol — seam for plugins that inject event fields.

Per ADR-0165 / ADR-0165.1, the spine's ``EmitPipeline`` asks every
enabled ``FieldProducer`` to contribute ``(key, value)`` pairs into
the ``payload`` of an ``EventRecord`` while it is being assembled.
Producers are sorted by ``priority`` (lowest first) and merged in
order; on key conflict the earlier writer wins, which lets low
priority numbers act as a stable override surface.

The Protocol mirrors the convention used by
``lca.infrastructure.observability.spine.derivers.base.Deriver``:
structural typing via ``@runtime_checkable`` so test doubles and
lightweight classes can opt in without inheriting from a base class.

The ``span`` argument is intentionally typed as ``Any`` because the
concrete ``SpineContext.SpanContext`` lives in the ``infrastructure``
layer and this module sits in ``contracts`` (import-linter forbids
``contracts -> infrastructure``). At runtime any object exposing the
attributes a producer cares about (e.g. ``span_id``,
``execution_point``) is acceptable.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

Phase = Literal["pre", "post", "exception"]


@runtime_checkable
class FieldProducer(Protocol):
    """A seam that injects auto-source fields into spine events.

    Attributes
    ----------
    name:
        Stable identifier used for debug logging and assembly order
        reporting. Convention: dotted string like ``spine.reflector.signature``.
    priority:
        Sort key for the ``EmitPipeline`` merge. Lower numbers run
        first; on key conflict the earlier writer wins.
    enabled:
        Profile-level toggle. ``EmitPipeline`` skips producers with
        ``enabled=False`` without removing them from the registry.
    """

    name: str
    priority: int
    enabled: bool

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
        """Return the fields this producer wants to inject.

        ``phase`` is one of:

        - ``"pre"`` — invoked before ``fn(*args, **kwargs)`` runs.
        - ``"post"`` — invoked after a successful return.
        - ``"exception"`` — invoked when ``fn`` raised; ``ctx.current_exception``
          is available.

        Returning an empty dict is the documented way for a producer
        to declare "no contribution for this phase".

        Reserved optional key
        ---------------------
        ``"_lca_failures"`` is reserved for producers that want to
        surface sub-field failures (e.g. ``SourceAttacher`` may fail
        to walk ``inspect``). When present, it MUST be a
        ``list[dict[str, Any]]`` with each entry shaped like::

            {"key": "locals_snapshot",
             "exception_class": "OSError",
             "traceback_text": "..."}

        ``EmitPipeline`` consumes the list and emits one
        ``spine.producer.failure`` journal event per entry through
        the same path as the main ``*.start`` event. Producers that
        never raise may omit the key entirely. The key is stripped
        from the merged payload before ``EventRecord`` sealing so
        it never leaks into the journal record itself.
        """
        ...
