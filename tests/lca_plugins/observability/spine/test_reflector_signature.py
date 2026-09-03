"""Tests for the ``spine.reflector.signature`` FieldProducer plugin.

Task 7.1: assert that ``SignatureFieldProducer.produce(phase="pre")``
returns the four canonical D11 signature auto-source keys:

- ``signature_fingerprint`` — sha256 of function source / qualname
- ``input_params``         — str repr of args/kwargs
- ``output_schema``         — typing.get_type_hints
- ``docstring_captured``    — first line of __doc__

The plugin is the first concrete implementation of the
``FieldProducer`` Protocol (ADR-0165 / ADR-0165.1); the test pins the
documented surface so future refactors do not silently drop keys.
"""

# ADR-0181 PR-5：signature reflector 是 D11 FieldProducer，本测试覆盖旧
# reflector 路径；PR-8 derivers 全迁时一并处理。
from __future__ import annotations

import pytest


pytestmark = pytest.mark.xfail(
    reason=(
        "ADR-0181 PR-5：旧 spine FieldProducer（context / signature / source）"
        " 已迁到 PR-8 derivers。本测试覆盖旧 reflector，本文件在 PR-8 旧 spine "
        "全退役时删（rg lca.plugins.observability.spine.reflectors.signature "
        "lca/ = 0 触发）。"
    ),
    strict=True,
)

import inspect
import typing
from typing import Any

from lca.contracts.observability.spine.producer import FieldProducer
from lca.plugins.observability.spine.reflectors.signature import (
    SignatureFieldProducer,
    setup,
)

# ── helpers ──────────────────────────────────────────────────────────


def _example(a: int, b: str = "x", *, flag: bool = True) -> int:
    """Example target used by the producer under test.

    The first line of this docstring is captured as
    ``docstring_captured``; the keyword-only ``flag`` parameter
    exercises ``inspect.signature`` on keyword-only args.
    """
    return a + len(b) + (1 if flag else 0)


# ── surface contract ────────────────────────────────────────────────


def test_produce_returns_all_required_keys() -> None:
    """``produce(phase='pre')`` MUST include the four documented keys."""
    producer = SignatureFieldProducer()
    args = (1,)
    kwargs = {"b": "hi", "flag": False}

    payload = producer.produce(
        fn=_example,
        args=args,
        kwargs=kwargs,
        ctx=object(),
        span=object(),
        phase="pre",
    )

    assert isinstance(payload, dict)
    assert "signature_fingerprint" in payload
    assert "input_params" in payload
    assert "output_schema" in payload
    assert "docstring_captured" in payload


def test_produce_satisfies_field_producer_protocol() -> None:
    """The producer MUST be a runtime-checkable FieldProducer."""
    producer = SignatureFieldProducer()
    assert isinstance(producer, FieldProducer)
    assert producer.name == "spine.reflector.signature"
    assert producer.enabled is True
    assert isinstance(producer.priority, int)


def test_signature_fingerprint_is_sha256_of_source_and_qualname() -> None:
    """Fingerprint MUST be a 64-char hex sha256 derived from source + qualname."""
    import hashlib

    producer = SignatureFieldProducer()
    payload = producer.produce(
        fn=_example,
        args=(1,),
        kwargs={"b": "hi"},
        ctx=object(),
        span=object(),
        phase="pre",
    )

    fingerprint = payload["signature_fingerprint"]
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64
    # Recompute independently to confirm deterministic composition.
    src = inspect.getsource(_example)
    expected = hashlib.sha256(f"{_example.__qualname__}\n{src}".encode()).hexdigest()
    assert fingerprint == expected


def test_input_params_is_str_repr_of_args_and_kwargs() -> None:
    """``input_params`` MUST be the str(...) of (args, kwargs)."""
    producer = SignatureFieldProducer()
    args = (1, 2)
    kwargs = {"flag": True}

    payload = producer.produce(
        fn=_example,
        args=args,
        kwargs=kwargs,
        ctx=object(),
        span=object(),
        phase="pre",
    )

    assert payload["input_params"] == str((args, kwargs))


def test_output_schema_matches_get_type_hints() -> None:
    """``output_schema`` MUST equal ``typing.get_type_hints(fn)``."""
    producer = SignatureFieldProducer()
    payload = producer.produce(
        fn=_example,
        args=(1,),
        kwargs={"b": "hi"},
        ctx=object(),
        span=object(),
        phase="pre",
    )

    assert payload["output_schema"] == typing.get_type_hints(_example)


def test_docstring_captured_is_first_line_of_doc() -> None:
    """``docstring_captured`` MUST be the first non-empty line of ``__doc__``."""
    producer = SignatureFieldProducer()
    payload = producer.produce(
        fn=_example,
        args=(1,),
        kwargs={},
        ctx=object(),
        span=object(),
        phase="pre",
    )

    expected_first_line = _example.__doc__.splitlines()[0].strip() if _example.__doc__ else ""
    assert payload["docstring_captured"] == expected_first_line


def test_handles_keyword_only_args() -> None:
    """Keyword-only args MUST not crash the fingerprint / repr path."""
    producer = SignatureFieldProducer()
    payload = producer.produce(
        fn=_example,
        args=(7,),
        kwargs={"flag": True},
        ctx=object(),
        span=object(),
        phase="pre",
    )

    # All four keys still present even though ``flag`` is keyword-only.
    assert "signature_fingerprint" in payload
    assert "input_params" in payload
    assert "output_schema" in payload
    assert "docstring_captured" in payload
    # Sanity: fingerprint is stable across repeated invocations.
    again = producer.produce(
        fn=_example,
        args=(7,),
        kwargs={"flag": True},
        ctx=object(),
        span=object(),
        phase="pre",
    )
    assert payload["signature_fingerprint"] == again["signature_fingerprint"]


def test_setup_is_registered_via_plugin_decorator() -> None:
    """The module MUST expose a plugin-decorated ``setup`` manifest entry."""
    # ``@plugin(...)`` returns a cordis ``Plugin`` carrier that wraps
    # the underlying ``setup`` coroutine. Cordis dispatches
    # ``plugin.setup(ctx, config)`` at boot, so the carrier must
    # expose ``.setup`` as a callable.
    assert hasattr(setup, "setup")
    assert callable(setup.setup)


# ── protocol surface stability ──────────────────────────────────────


def test_priority_and_name_are_stable_strings() -> None:
    """Name and priority are part of the merge contract — pin them."""
    producer = SignatureFieldProducer()
    assert producer.name == "spine.reflector.signature"
    # priority is implementation-defined but must be a non-negative int.
    assert producer.priority >= 0


def test_disabled_producer_still_has_intact_state() -> None:
    """Toggling ``enabled`` MUST NOT clear ``name`` / ``priority``."""
    producer = SignatureFieldProducer()
    producer.enabled = False
    assert producer.name == "spine.reflector.signature"
    assert isinstance(producer.priority, int)


# Allow pytest to inspect ``Any`` typing without warning on Python 3.12.
_ = Any
