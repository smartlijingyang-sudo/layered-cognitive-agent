"""Behavioral tests for ``lca.harness.profile.resolve.privilege_projection``.

ADR-0199 §3.1 + I-HPC-5: ``meta.privileges`` is the fourth orthogonal
contract dimension; undeclared privilege triggers fail-closed at setup.
The projector is pure-data normalisation: shape validation + deterministic
order-preserving dedup (C8). Unknown-prefix gating lives in
``PluginContract.__post_init__``, not here.
"""

from __future__ import annotations

import pytest

from lca.harness.profile.resolve.privilege_projection import (
    PrivilegeProjectionError,
    project_privileges,
)

# ---------------------------------------------------------------------------
# Empty / missing key
# ---------------------------------------------------------------------------


def test_empty_meta_returns_empty_tuple() -> None:
    """``project_privileges(None)`` → ``()`` (backward-compatible default)."""
    assert project_privileges(None) == ()


def test_missing_privileges_key_returns_empty_tuple() -> None:
    """meta without the ``privileges`` key → ``()``."""
    assert project_privileges({}) == ()
    assert project_privileges({"other": "value"}) == ()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_simple_privileges_tuple() -> None:
    """A list of privilege strings is preserved verbatim."""
    result = project_privileges({"privileges": ["journal.append", "state.write"]})
    assert result == ("journal.append", "state.write")


def test_privileges_list_accepted() -> None:
    """``list`` input container is accepted (in addition to ``tuple``)."""
    assert project_privileges({"privileges": ["a", "b"]}) == ("a", "b")


def test_privileges_preserves_order() -> None:
    """Order of first appearance is preserved (C8 deterministic)."""
    result = project_privileges({"privileges": ["network.egress", "journal.append", "memory.read"]})
    assert result == ("network.egress", "journal.append", "memory.read")


def test_privileges_dedupes() -> None:
    """Duplicate entries collapse; first occurrence wins."""
    result = project_privileges({"privileges": ["a", "b", "a", "c", "b"]})
    assert result == ("a", "b", "c")


def test_privileges_with_one_element_dedup_works() -> None:
    """Single-element list still dedupes (trivial case)."""
    assert project_privileges({"privileges": ["x"]}) == ("x",)
    assert project_privileges({"privileges": ["x", "x"]}) == ("x",)


# ---------------------------------------------------------------------------
# Shape rejection
# ---------------------------------------------------------------------------


def test_privileges_rejects_non_list_input() -> None:
    """Strings / dicts / sets are not valid containers."""
    for bad in ["journal.append", {"journal.append"}, {"a": "b"}, 42]:
        with pytest.raises(PrivilegeProjectionError, match="list or tuple"):
            project_privileges({"privileges": bad})


def test_privileges_rejects_non_string_element() -> None:
    """Non-string elements (ints, None, dicts) are rejected."""
    with pytest.raises(PrivilegeProjectionError, match=r"privileges\[1\]"):
        project_privileges({"privileges": ["ok", 42, "also_ok"]})


def test_privileges_rejects_empty_string() -> None:
    """Empty strings are not valid privilege names (I-HPC-5 fail-closed)."""
    with pytest.raises(PrivilegeProjectionError, match="non-empty"):
        project_privileges({"privileges": ["journal.append", ""]})


def test_privileges_rejects_mixed_types() -> None:
    """Mixed str + non-str elements still raise on the bad index."""
    with pytest.raises(PrivilegeProjectionError, match=r"privileges\[2\]"):
        project_privileges({"privileges": ["a", "b", None, "c"]})


# ---------------------------------------------------------------------------
# Return type guarantees
# ---------------------------------------------------------------------------


def test_privileges_returned_tuple_is_frozen() -> None:
    """Result is a frozen ``tuple`` (immutable, C8 + contracts purity)."""
    result = project_privileges({"privileges": ["x"]})
    assert isinstance(result, tuple)
    with pytest.raises(TypeError):
        result[0] = "y"  # type: ignore[index]


def test_privileges_returned_tuple_cannot_be_appended() -> None:
    """Returned tuple rejects item assignment at any index."""
    result = project_privileges({"privileges": ["a", "b"]})
    with pytest.raises((AttributeError, TypeError)):
        result[1] = "c"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Error type contract
# ---------------------------------------------------------------------------


def test_privilege_projection_error_is_value_error() -> None:
    """``PrivilegeProjectionError`` is a ``ValueError`` (caller ergonomics)."""
    assert issubclass(PrivilegeProjectionError, ValueError)
    # Caught by callers that only catch ValueError
    try:
        raise PrivilegeProjectionError("boom")
    except ValueError as exc:
        assert "boom" in str(exc)


# ---------------------------------------------------------------------------
# Orthogonality to other meta fields
# ---------------------------------------------------------------------------


def test_privileges_orthogonal_to_provides() -> None:
    """Projector only reads ``privileges``; other meta keys are ignored."""
    meta = {
        "privileges": ["journal.append"],
        "provides": ["memory.semantic"],
        "requires": ["state_store"],
        "kind": "provider",
        "id": "test.plugin",
    }
    assert project_privileges(meta) == ("journal.append",)


def test_privileges_does_not_mutate_input_meta() -> None:
    """Pure function: input mapping is not mutated by projection."""
    meta = {"privileges": ["a", "b", "a"]}
    snapshot = dict(meta)
    project_privileges(meta)
    assert meta == snapshot


# ---------------------------------------------------------------------------
# Determinism (C8)
# ---------------------------------------------------------------------------


def test_privileges_deterministic_across_calls() -> None:
    """Same input → same output across repeated calls (C8 determinism)."""
    meta = {"privileges": ["journal.append", "state.write", "journal.append"]}
    first = project_privileges(meta)
    second = project_privileges(meta)
    third = project_privileges(dict(meta))  # also a fresh mapping
    assert first == second == third == ("journal.append", "state.write")


def test_privileges_dedup_preserves_first_occurrence_order() -> None:
    """When duplicates exist, first occurrence's position wins (C8)."""
    result = project_privileges({"privileges": ["b", "a", "b", "a", "c"]})
    assert result == ("b", "a", "c")


def test_privileges_with_unknown_prefix_passes_through() -> None:
    """Unknown prefixes are NOT an error at this seam (forward-compat).

    Per ADR-0199 §3.1, the projector is purely declarative. The
    closed-set gate lives in :meth:`PluginContract.__post_init__` so
    adding a new prefix can be done without rewriting this helper.
    """
    assert project_privileges({"privileges": ["unknown.future.thing"]}) == ("unknown.future.thing",)
