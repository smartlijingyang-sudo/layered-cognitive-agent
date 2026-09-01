"""Tests for the ``spine.reflector.source`` FieldProducer plugin.

Task 9.1: ``SourceAttacher`` captures ``source_location``,
``call_frames`` (up to 10 frames), and a redacted ``locals_snapshot``
(≤ 4 KB UTF-8) for every ``*.start`` event. The two required tests
from the brief pin the call-site capture and the secret-redaction
behaviour; the surrounding cases pin the rest of the surface so
follow-up refactors do not silently drop fields.
"""

from __future__ import annotations

import re
from typing import Any

from lca.contracts.observability.spine.producer import FieldProducer

# ── helpers ──────────────────────────────────────────────────────────


def _call_source_attacher(
    producer: object, *, fn: object, args: tuple, kwargs, ctx
) -> dict[str, Any]:
    """Invoke ``producer.produce(...)`` with the required FieldProducer kwargs.

    The brief's tests hand-build the same call shape; centralising it
    here keeps the assertions focused on the returned payload.
    """
    raw: dict[str, Any] = producer.produce(  # type: ignore[attr-defined]
        fn=fn,
        args=args,
        kwargs=kwargs,
        ctx=ctx,
        span=None,
        phase="pre",
    )
    return raw


# ── Step 1: call-site capture ────────────────────────────────────────


def test_source_attacher_captures_call_site() -> None:
    """``source_location`` MUST pin the file, line, and function of the call site.

    Mirrors the brief exactly: a nested ``a_function`` invokes
    ``src.produce(...)`` and asserts the resulting ``source_location``
    points back at this test file and at the function ``a_function``.
    """
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    src = SourceAttacher()

    def a_function():
        # source location of *this* call is test file at line N
        return src.produce(fn=a_function, args=(), kwargs={}, ctx=None, span=None, phase="pre")

    fields = a_function()
    assert "source_location" in fields
    assert fields["source_location"].file.endswith("test_source_attacher.py")
    assert fields["source_location"].function == "a_function"


# ── Step 2: secret redaction ────────────────────────────────────────


def test_source_attacher_redacts_secrets() -> None:
    """``locals_snapshot`` MUST redact values matching ``redact_patterns``.

    The brief uses ``sk-abc123def4567890xyz`` (matches
    ``r"sk-[A-Za-z0-9]{16,}"``) — the value MUST NOT appear in any
    snapshot entry. ``ctx.token`` flows through ``ctx.__dict__``
    into the locals scan so the redaction actually has something
    to redact.
    """
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    src = SourceAttacher(redact_patterns=[r"sk-[A-Za-z0-9]{16,}"])
    sensitive_value = "sk-abc123def4567890xyz"
    fields = src.produce(
        fn=lambda: None,
        args=(),
        kwargs=None,
        ctx=type("Ctx", (), {"token": sensitive_value})(),
        span=None,
        phase="pre",
    )
    snapshot = fields["locals_snapshot"].pre_call
    assert all("sk-abc" not in v for v in snapshot.values())


# ── Protocol conformance & surface ───────────────────────────────────


def test_source_attacher_satisfies_field_producer_protocol() -> None:
    """``SourceAttacher`` MUST structurally implement ``FieldProducer``."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    producer = SourceAttacher()
    assert isinstance(producer, FieldProducer)


def test_source_attacher_metadata() -> None:
    """Stable name / priority / enabled attrs."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    producer = SourceAttacher()
    assert producer.name == "spine.reflector.source"
    assert producer.priority == 8
    assert producer.enabled is True


def test_call_frames_contains_at_most_ten_frames() -> None:
    """``call_frames`` MUST contain at most 10 ``{file, line, function}`` entries."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    producer = SourceAttacher()
    fields = _call_source_attacher(producer, fn=lambda: None, args=(), kwargs={}, ctx=None)

    frames = fields["call_frames"]
    assert isinstance(frames, list)
    assert 1 <= len(frames) <= 10
    for frame in frames:
        assert {"file", "line", "function"} <= set(frame.keys())


def test_source_location_has_required_keys() -> None:
    """``source_location`` MUST have ``file`` / ``line`` / ``function``."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    producer = SourceAttacher()
    fields = _call_source_attacher(producer, fn=lambda: None, args=(), kwargs={}, ctx=None)

    location = fields["source_location"]
    assert {"file", "line", "function"} <= set(location.keys())
    assert isinstance(location["file"], str)
    assert isinstance(location["line"], int)
    assert isinstance(location["function"], str)


def test_locals_snapshot_is_capped_at_max_locals_bytes() -> None:
    """The total UTF-8 size of ``pre_call`` MUST NOT exceed ``max_locals_bytes``."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    cap = 1024  # tighter cap than 4 KB so the test runs fast.
    producer = SourceAttacher(max_locals_bytes=cap)

    class Ctx:
        big = "x" * (cap * 4)

    fields = _call_source_attacher(producer, fn=lambda: None, args=(), kwargs={}, ctx=Ctx())
    snapshot = fields["locals_snapshot"].pre_call

    encoded = "".join(
        value for envelope in snapshot.values() for value in envelope.values()
    ).encode("utf-8")
    assert len(encoded) <= cap


def test_locals_snapshot_includes_ctx_attributes() -> None:
    """Attribute-style ctx entries MUST be reachable via the scan."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    producer = SourceAttacher()

    class Ctx:
        visible_marker = "marker-abc-123"

    fields = _call_source_attacher(producer, fn=lambda: None, args=(), kwargs={}, ctx=Ctx())
    snapshot = fields["locals_snapshot"].pre_call

    assert "ctx" in snapshot
    assert "visible_marker" in snapshot["ctx"]
    assert "marker-abc-123" in snapshot["ctx"]["visible_marker"]


def test_default_redact_patterns_replace_api_key_assignment() -> None:
    """Default patterns MUST redact ``api_key=...``-style assignments."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    producer = SourceAttacher()  # default patterns only

    class Ctx:
        creds = "api_key=hunter2secret"

    fields = _call_source_attacher(producer, fn=lambda: None, args=(), kwargs={}, ctx=Ctx())
    snapshot = fields["locals_snapshot"].pre_call

    creds_repr = snapshot.get("ctx", {}).get("creds", "")
    assert "hunter2secret" not in creds_repr


def test_redaction_replaces_value_with_stars() -> None:
    """Redacted values MUST be visible as ``"***"`` (not stripped silently)."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    producer = SourceAttacher(redact_patterns=[r"sk-[A-Za-z0-9]{16,}"])
    sensitive_value = "sk-abc123def4567890xyz"

    fields = _call_source_attacher(
        producer,
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=type("Ctx", (), {"token": sensitive_value})(),
    )
    snapshot = fields["locals_snapshot"].pre_call

    token_repr = snapshot["ctx"]["token"]
    assert token_repr == "***"  # noqa: S105 — checking the redacted sentinel.


def test_env_style_secret_keys_redact_their_values() -> None:
    """Env-style KEY/SECRET/PASSWORD/TOKEN names MUST also trigger redaction."""
    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    producer = SourceAttacher()
    sensitive_value = "sk-abc123def4567890xyz"

    class Ctx:
        OPENAI_API_KEY = sensitive_value

    fields = _call_source_attacher(
        producer,
        fn=lambda: None,
        args=(),
        kwargs={},
        ctx=Ctx(),
    )
    snapshot = fields["locals_snapshot"].pre_call

    api_repr = snapshot.get("ctx", {}).get("OPENAI_API_KEY", "")
    assert "sk-abc" not in api_repr


def test_redaction_pattern_compiles() -> None:
    """Constructor MUST compile provided patterns; invalid regex raises ``re.error``."""
    import re as _re

    from lca.plugins.observability.spine.reflectors.source import SourceAttacher

    try:
        SourceAttacher(redact_patterns=[r"[unbalanced"])
    except _re.error:
        return
    raise AssertionError("invalid regex should have raised re.error")


def test_setup_is_registered_via_plugin_decorator() -> None:
    """The module MUST expose a plugin-decorated ``setup`` carrier."""
    from lca.plugins.observability.spine.reflectors.source import setup

    assert hasattr(setup, "setup")
    assert callable(setup.setup)


def test_plugin_manifest_declares_expected_metadata() -> None:
    """The wrapped plugin exposes the canonical id / layer / kind / provides."""
    from lca.harness.plugin_declaration import definition_from_plugin
    from lca.plugins.observability.spine import reflectors

    assert hasattr(reflectors.source, "setup")

    definition = definition_from_plugin(reflectors.source.setup, module=__name__)
    assert definition.id == "spine.reflector.source"
    assert definition.spec.layer == "L0"
    assert definition.provided_capability_keys == ("field_producer.source",)


def test_module_export_surface() -> None:
    """``SourceAttacher`` is part of the module's public surface."""
    import lca.plugins.observability.spine.reflectors.source as source_module

    assert hasattr(source_module, "SourceAttacher")
    assert "SourceAttacher" in source_module.__all__


# Silence "imported but unused" lint warnings for the regex re-import
# used inside the body of test_redaction_pattern_compiles.
_ = re
