"""activation_ref pure hash determinism + shape (ADR-0199 §2.2.2 / C8)."""

from __future__ import annotations

import hashlib
import os
import time
from collections import OrderedDict
from unittest.mock import patch

import pytest

from lca.harness.runtime.activation_ref import (
    _ACTIVATION_HASH_NAMESPACE,
    compute_activation_ref,
    is_activation_ref,
)

_PLAN_REF = "abcdef0123456789"
_GRAPH_REF = "graph-001"
_PLUGIN_SET_REF = "plugin-set-A"
_SESSION_ID = "session-xyz"


class TestDeterminism:
    """Same inputs must produce the same activation_ref (idempotent)."""

    def test_same_inputs_same_hash(self) -> None:
        a = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        b = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert a == b

    def test_100_iterations_same_input_same_hash(self) -> None:
        seen = set()
        for _ in range(100):
            seen.add(
                compute_activation_ref(
                    plan_ref=_PLAN_REF,
                    graph_ref=_GRAPH_REF,
                    plugin_set_ref=_PLUGIN_SET_REF,
                    session_id=_SESSION_ID,
                )
            )
        assert len(seen) == 1


class TestShape:
    """activation_ref must be self-describing and parseable."""

    def test_hash_format(self) -> None:
        ref = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert ref.startswith(f"{_ACTIVATION_HASH_NAMESPACE}:")
        hex_part = ref[len(f"{_ACTIVATION_HASH_NAMESPACE}:") :]
        assert len(hex_part) == 64
        assert all(c in "0123456789abcdef" for c in hex_part)

    def test_hash_matches_manual_sha256(self) -> None:
        """The hash must equal a hand-computed sha256 of canonical JSON."""
        import json as _json

        canonical = _json.dumps(
            {
                "session_id": _SESSION_ID,
                "plan_ref": _PLAN_REF,
                "graph_ref": _GRAPH_REF,
                "plugin_set_ref": _PLUGIN_SET_REF,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        expected_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        expected = f"{_ACTIVATION_HASH_NAMESPACE}:{expected_digest}"
        actual = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert actual == expected


class TestOrderIndependence:
    """Calling with reordered keyword args must yield the same hash."""

    def test_order_independent(self) -> None:
        ref_a = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        # Reorder kwargs
        ref_b = compute_activation_ref(
            session_id=_SESSION_ID,
            plugin_set_ref=_PLUGIN_SET_REF,
            graph_ref=_GRAPH_REF,
            plan_ref=_PLAN_REF,
        )
        assert ref_a == ref_b


class TestDistinctness:
    """Each input field must contribute to the hash."""

    def test_session_id_distinguishes_activation(self) -> None:
        ref_a = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id="session-A",
        )
        ref_b = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id="session-B",
        )
        assert ref_a != ref_b

    def test_plan_ref_change_yields_new_hash(self) -> None:
        ref_a = compute_activation_ref(
            plan_ref="plan-1",
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        ref_b = compute_activation_ref(
            plan_ref="plan-2",
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert ref_a != ref_b

    def test_graph_ref_change_yields_new_hash(self) -> None:
        ref_a = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref="graph-A",
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        ref_b = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref="graph-B",
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert ref_a != ref_b

    def test_plugin_set_ref_change_yields_new_hash(self) -> None:
        ref_a = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref="plugins-A",
            session_id=_SESSION_ID,
        )
        ref_b = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref="plugins-B",
            session_id=_SESSION_ID,
        )
        assert ref_a != ref_b


class TestTypeGuard:
    """is_activation_ref must accept its own output and reject imposters."""

    def test_is_activation_ref_accepts_own_output(self) -> None:
        ref = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert is_activation_ref(ref) is True

    def test_is_activation_ref_accepts_another_valid_ref(self) -> None:
        # Independently constructed but still well-formed
        ref = f"{_ACTIVATION_HASH_NAMESPACE}:" + "0" * 64
        assert is_activation_ref(ref) is True

    def test_is_activation_ref_rejects_other_strings(self) -> None:
        assert is_activation_ref("") is False
        assert is_activation_ref("not-a-hash") is False
        assert is_activation_ref("abc") is False

    def test_is_activation_ref_rejects_wrong_namespace(self) -> None:
        # sha256 hex length but wrong prefix
        bad = "lca.wrong:" + "0" * 64
        assert is_activation_ref(bad) is False

    def test_is_activation_ref_rejects_wrong_length(self) -> None:
        # Right prefix, wrong hex length
        too_short = f"{_ACTIVATION_HASH_NAMESPACE}:" + "0" * 16
        too_long = f"{_ACTIVATION_HASH_NAMESPACE}:" + "0" * 80
        assert is_activation_ref(too_short) is False
        assert is_activation_ref(too_long) is False

    def test_is_activation_ref_rejects_non_hex_chars(self) -> None:
        # Right length, wrong alphabet (uppercase, g-z)
        bad_upper = f"{_ACTIVATION_HASH_NAMESPACE}:" + "F" * 64
        bad_letter = f"{_ACTIVATION_HASH_NAMESPACE}:" + "g" * 64
        assert is_activation_ref(bad_upper) is False
        assert is_activation_ref(bad_letter) is False


class TestDeterminismInvariants:
    """C8: no env reads, no clock reads, no PID reads."""

    def test_no_env_reads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Setting a fake env var must not change the hash."""
        monkeypatch.setenv("LCA_ACTIVATION_REF_TEST_VAR", "polluted")
        before = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        monkeypatch.setenv("LCA_ACTIVATION_REF_TEST_VAR", "different-value")
        after = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert before == after
        # Sanity: the env var was actually set
        assert os.environ.get("LCA_ACTIVATION_REF_TEST_VAR") == "different-value"

    def test_no_clock_reads(self) -> None:
        """Mocking time.time / time.monotonic must not change the hash."""
        before = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )

        with (
            patch.object(time, "time", return_value=1234567890.0),
            patch.object(time, "monotonic", return_value=999.0),
        ):
            after = compute_activation_ref(
                plan_ref=_PLAN_REF,
                graph_ref=_GRAPH_REF,
                plugin_set_ref=_PLUGIN_SET_REF,
                session_id=_SESSION_ID,
            )

        assert before == after


class TestKeywordOnlySignature:
    """The signature must be keyword-only (call-site self-documenting)."""

    def test_keyword_only_arguments(self) -> None:
        # Positional invocation must fail (the * separator forbids it).
        with pytest.raises(TypeError):
            compute_activation_ref(  # type: ignore[misc]
                _PLAN_REF,
                _GRAPH_REF,
                _PLUGIN_SET_REF,
                _SESSION_ID,
            )


class TestPayloadConstruction:
    """The internal payload dict construction must use a dict (not OrderedDict
    dependency on insertion order — sort_keys=True normalizes either way)."""

    def test_explicit_ordered_dict_input(self) -> None:
        """Even when caller passes OrderedDict-shaped payloads, output is stable."""
        # This exercises the underlying json sort_keys contract: build an
        # OrderedDict with reverse insertion and feed its values in.
        ordered = OrderedDict(
            [
                ("plugin_set_ref", _PLUGIN_SET_REF),
                ("graph_ref", _GRAPH_REF),
                ("plan_ref", _PLAN_REF),
                ("session_id", _SESSION_ID),
            ]
        )
        ref_via_kw = compute_activation_ref(**ordered)
        ref_via_normal = compute_activation_ref(
            plan_ref=_PLAN_REF,
            graph_ref=_GRAPH_REF,
            plugin_set_ref=_PLUGIN_SET_REF,
            session_id=_SESSION_ID,
        )
        assert ref_via_kw == ref_via_normal
