"""Tests for ``spine.reflector.context`` plugin (Task 7.2).

The plugin contributes a ``FieldProducer`` that injects budget,
preconditions, circuit-breaker state, post-state delta, and
side-effect fields into spine ``EventRecord`` payloads. This test
guards the structural Protocol contract, the two phase dicts
required by ADR-0165.1 §7.5.3, and the plugin manifest shape so
profile boot picks the producer up via
``ctx.require("field_producer.context")``.
"""

from __future__ import annotations

# ── protocol conformance ─────────────────────────────────────────────


def test_context_field_producer_satisfies_field_producer_protocol() -> None:
    """``ContextFieldProducer`` structurally implements ``FieldProducer``."""
    from lca.contracts.observability.spine.producer import FieldProducer
    from lca.plugins.observability.spine.reflectors.context import (
        ContextFieldProducer,
    )

    producer = ContextFieldProducer()
    assert isinstance(producer, FieldProducer)


def test_context_field_producer_metadata() -> None:
    """Producer exposes the ``name`` / ``priority`` / ``enabled`` seam attrs."""
    from lca.plugins.observability.spine.reflectors.context import (
        ContextFieldProducer,
    )

    producer = ContextFieldProducer()
    assert producer.name == "spine.reflector.context"
    assert isinstance(producer.priority, int)
    assert producer.enabled is True


# ── phase dicts ──────────────────────────────────────────────────────


def test_produce_pre_phase_returns_required_keys() -> None:
    """``produce(phase="pre")`` returns ``preconditions`` + ``budget_at_entry``."""
    from lca.plugins.observability.spine.reflectors.context import (
        ContextFieldProducer,
    )

    producer = ContextFieldProducer()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="pre",
    )

    assert "preconditions" in payload
    assert "budget_at_entry" in payload


def test_produce_post_phase_returns_required_keys() -> None:
    """``produce(phase="post")`` returns the four post-side fields."""
    from lca.plugins.observability.spine.reflectors.context import (
        ContextFieldProducer,
    )

    producer = ContextFieldProducer()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="post",
    )

    assert "post_state_delta" in payload
    assert "budget_consumed" in payload
    assert "circuit_breaker_state" in payload
    assert "side_effects_added" in payload


def test_produce_other_phase_returns_empty_dict() -> None:
    """Phases outside ``pre`` / ``post`` return ``{}`` (no contribution)."""
    from lca.plugins.observability.spine.reflectors.context import (
        ContextFieldProducer,
    )

    producer = ContextFieldProducer()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="exception",
    )

    assert payload == {}


# ── default placeholder values ──────────────────────────────────────


def test_pre_phase_defaults_when_ctx_is_none() -> None:
    """Without a SpineContext, placeholders are well-formed strings."""
    from lca.plugins.observability.spine.reflectors.context import (
        ContextFieldProducer,
    )

    producer = ContextFieldProducer()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="pre",
    )

    assert isinstance(payload["preconditions"], str)
    # ``budget_at_entry`` defaults to an empty dict when no SpineContext
    # is wired — real values flow in from ``wrap_instrument`` in a later PR.
    assert payload["budget_at_entry"] == {}


def test_post_phase_defaults_when_ctx_is_none() -> None:
    """Without context, circuit breaker reports ``"closed"`` and the rest empty."""
    from lca.plugins.observability.spine.reflectors.context import (
        ContextFieldProducer,
    )

    producer = ContextFieldProducer()
    payload = producer.produce(
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=None,
        span=None,
        phase="post",
    )

    assert payload["circuit_breaker_state"] == "closed"
    assert payload["post_state_delta"] == {}
    assert payload["budget_consumed"] == {}
    assert payload["side_effects_added"] == ()


# ── plugin manifest shape ───────────────────────────────────────────


def test_plugin_manifest_declares_expected_metadata() -> None:
    """The wrapped plugin exposes the canonical id / layer / kind / provides."""
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine import reflectors

    # Touching the module forces the @plugin decorator to attach
    # ``_lca_definition`` onto the carrier.
    assert hasattr(reflectors.context, "setup")

    definition = definition_from_plugin(reflectors.context.setup, module=__name__)
    assert definition.id == "spine.reflector.context"
    assert definition.spec.layer == "L0"
    assert definition.provided_capability_keys == ("field_producer.context",)


def test_module_export_surface() -> None:
    """The module exposes ``ContextFieldProducer`` in its public surface."""
    import lca.plugins.observability.spine.reflectors.context as ctx_module

    assert hasattr(ctx_module, "ContextFieldProducer")
    assert "ContextFieldProducer" in ctx_module.__all__
