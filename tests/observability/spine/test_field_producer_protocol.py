"""Tests for the FieldProducer Protocol (Task 3.0).

A ``FieldProducer`` is the seam that lets spine plugin authors inject
``(key, value)`` pairs into ``EventRecord.payload`` while the spine is
emitting an event. The ``EmitPipeline`` assembles every enabled
producer by ``priority`` and merges the dicts (low-priority wins on
conflict). Per ADR-0165.1 the seam is closed: every reflector /
classifier / deriver that wants to contribute fields must satisfy
``FieldProducer``.

These tests guard the structural contract:
1. ``FieldProducer`` is a ``Protocol`` exposing ``produce``.
2. A class with the right attributes and method is recognised by
   ``isinstance(obj, FieldProducer)`` thanks to
   ``@runtime_checkable`` — this is what lets lightweight test
   doubles and plugin classes opt in without inheriting.
"""

from __future__ import annotations

from typing import Any


def test_field_producer_is_protocol() -> None:
    """FieldProducer is a Protocol class exposing ``produce``."""
    from lca.contracts.observability.spine.producer import FieldProducer

    assert hasattr(FieldProducer, "produce")
    # Protocol classes define ``__call__`` on instances only; the
    # class itself has the abstract method declared as an attribute.
    assert callable(getattr(FieldProducer, "produce", None))


def test_field_producer_satisfied_by_structural_class() -> None:
    """A bare class with the right attribute set is a FieldProducer."""
    from lca.contracts.observability.spine.producer import FieldProducer

    class GoodProducer:
        name = "test.producer"
        priority = 10
        enabled = True

        def produce(
            self,
            *,
            fn: Any,
            args: tuple[Any, ...],
            kwargs: dict[str, Any],
            ctx: Any,
            span: Any,
            phase: str,
        ) -> dict[str, Any]:
            return {"marker": self.name, "phase": phase}

    p = GoodProducer()
    assert isinstance(p, FieldProducer)
    assert p.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="pre",
    ) == {"marker": "test.producer", "phase": "pre"}


def test_field_producer_re_exported_from_spine_package() -> None:
    """``lca.contracts.observability.spine`` re-exports ``FieldProducer``."""
    from lca.contracts.observability.spine import FieldProducer as ReExported
    from lca.contracts.observability.spine.producer import FieldProducer

    assert ReExported is FieldProducer
