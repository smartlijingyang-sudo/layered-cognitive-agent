"""Behavioral tests for ``lca.harness.composition.resource_registry``.

ADR-0199 §3.1 + I-HPC-6: ``resources`` is the 4th orthogonal contract
dimension (read-only content). The projector is pure-data normalisation:
shape validation + deterministic sort + dedup (C8). The registry is a
thin container — it does NOT register executable capabilities.
"""

from __future__ import annotations

import pytest

from lca.contracts.runtime.resource import ResourceId
from lca.harness.composition.resource_registry import (
    ResourceProjectionError,
    ResourceRegistry,
    project_resources,
)

# ---------------------------------------------------------------------------
# project_resources — empty / missing inputs
# ---------------------------------------------------------------------------


def test_empty_meta_returns_empty_tuple() -> None:
    """``project_resources(None)`` → ``()`` (backward-compatible default)."""
    assert project_resources(None) == ()


def test_missing_resources_key_returns_empty_tuple() -> None:
    """meta without the ``resources`` key → ``()``."""
    assert project_resources({}) == ()
    assert project_resources({"other": "value"}) == ()


# ---------------------------------------------------------------------------
# project_resources — happy paths
# ---------------------------------------------------------------------------


def test_string_ref_projection() -> None:
    """A list of canonical ref strings parses to ResourceId tuple (sorted)."""
    meta = {"resources": ["skill:memory/retrieval", "prompt:coding_agent/system"]}
    assert project_resources(meta) == (
        ResourceId(kind="prompt", namespace="coding_agent", name="system"),
        ResourceId(kind="skill", namespace="memory", name="retrieval"),
    )


def test_dict_projection() -> None:
    """A list of dicts (kind/namespace/name) projects to ResourceId tuple (sorted)."""
    meta = {
        "resources": [
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
            {"kind": "role", "namespace": "assistants", "name": "solo"},
        ]
    }
    assert project_resources(meta) == (
        ResourceId(kind="role", namespace="assistants", name="solo"),
        ResourceId(kind="skill", namespace="memory", name="retrieval"),
    )


def test_resource_id_passthrough() -> None:
    """Pre-formed ResourceId instances project to a sorted tuple (C8)."""
    rid1 = ResourceId(kind="skill", namespace="memory", name="retrieval")
    rid2 = ResourceId(kind="prompt", namespace="coding_agent", name="system")
    assert project_resources({"resources": [rid1, rid2]}) == (rid2, rid1)


def test_mixed_input_types_in_one_list() -> None:
    """Mixed input shapes (str / dict / ResourceId) all project correctly (sorted)."""
    rid = ResourceId(kind="role", namespace="assistants", name="solo")
    meta = {
        "resources": [
            "skill:memory/retrieval",
            {"kind": "prompt", "namespace": "coding_agent", "name": "system"},
            rid,
        ]
    }
    assert project_resources(meta) == (
        ResourceId(kind="prompt", namespace="coding_agent", name="system"),
        ResourceId(kind="role", namespace="assistants", name="solo"),
        ResourceId(kind="skill", namespace="memory", name="retrieval"),
    )


# ---------------------------------------------------------------------------
# project_resources — shape rejection
# ---------------------------------------------------------------------------


def test_invalid_string_ref_raises_projection_error() -> None:
    """Malformed string refs raise ResourceProjectionError (not ValueError)."""
    with pytest.raises(ResourceProjectionError, match="string ref is invalid"):
        project_resources({"resources": ["not-a-valid-ref"]})


def test_invalid_dict_missing_key_raises_projection_error() -> None:
    """Dict entries missing required keys raise ResourceProjectionError."""
    with pytest.raises(ResourceProjectionError, match=r"missing key 'name'"):
        project_resources({"resources": [{"kind": "skill", "namespace": "memory"}]})


def test_invalid_kind_raises_projection_error() -> None:
    """Unknown kind in string ref raises ResourceProjectionError."""
    with pytest.raises(ResourceProjectionError, match="string ref is invalid"):
        project_resources({"resources": ["unknown:memory/retrieval"]})


def test_reserved_namespace_raises_projection_error() -> None:
    """Reserved namespaces (``system``, ``internal``, ``_reserved``) raise."""
    with pytest.raises(ResourceProjectionError, match="dict is invalid"):
        project_resources({"resources": [{"kind": "skill", "namespace": "system", "name": "core"}]})


def test_non_list_resources_raises_projection_error() -> None:
    """``meta.resources`` must be a list/tuple — strings/dicts/sets rejected."""
    for bad in ["a-string", {"a": "dict"}, 42, {"skill:memory/x"}]:
        with pytest.raises(ResourceProjectionError, match="list or tuple"):
            project_resources({"resources": bad})


def test_unsupported_item_type_raises_projection_error() -> None:
    """Items must be str / Mapping / ResourceId — not ints / None / lists."""
    with pytest.raises(ResourceProjectionError, match=r"must be a string, dict"):
        project_resources({"resources": ["skill:memory/x", 42]})


# ---------------------------------------------------------------------------
# project_resources — dedup + ordering (C8)
# ---------------------------------------------------------------------------


def test_deduplicates_identical_resources() -> None:
    """Identical entries (by canonical ref) collapse to one."""
    meta = {
        "resources": [
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
            "skill:memory/retrieval",
        ]
    }
    assert project_resources(meta) == (
        ResourceId(kind="skill", namespace="memory", name="retrieval"),
    )


def test_result_sorted_by_to_ref() -> None:
    """Output is sorted by ``to_ref()`` regardless of input order (C8)."""
    meta = {
        "resources": [
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
            {"kind": "skill", "namespace": "coding", "name": "refactor"},
            {"kind": "prompt", "namespace": "coding_agent", "name": "system"},
        ]
    }
    result = project_resources(meta)
    refs = [r.to_ref() for r in result]
    assert refs == sorted(refs)
    assert refs == [
        "prompt:coding_agent/system",
        "skill:coding/refactor",
        "skill:memory/retrieval",
    ]


def test_no_io_side_effects_in_projection() -> None:
    """Projection must not mutate input mapping (pure function)."""
    meta = {
        "resources": [
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
        ]
    }
    snapshot = {
        "resources": [
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
        ]
    }
    project_resources(meta)
    assert meta == snapshot


def test_projection_deterministic_across_calls() -> None:
    """Same input → same output across repeated calls (C8 determinism)."""
    meta = {
        "resources": [
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},
            {"kind": "skill", "namespace": "coding", "name": "refactor"},
            {"kind": "skill", "namespace": "memory", "name": "retrieval"},  # dup
        ]
    }
    first = project_resources(meta)
    second = project_resources(meta)
    third = project_resources(dict(meta))
    assert first == second == third


# ---------------------------------------------------------------------------
# ResourceRegistry — construction & basic operations
# ---------------------------------------------------------------------------


def test_resource_registry_construct_from_tuple() -> None:
    """Constructing from a Sequence of ResourceIds populates the registry."""
    rid1 = ResourceId(kind="skill", namespace="memory", name="retrieval")
    rid2 = ResourceId(kind="prompt", namespace="coding_agent", name="system")
    registry = ResourceRegistry([rid1, rid2])
    assert len(registry) == 2


def test_resource_registry_construct_default_empty() -> None:
    """Default-constructed registry has zero entries."""
    registry = ResourceRegistry()
    assert len(registry) == 0
    assert registry.resources == ()


def test_resource_registry_contains_resource_id() -> None:
    """``__contains__`` accepts ResourceId instances."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    assert rid in registry


def test_resource_registry_contains_string_ref() -> None:
    """``__contains__`` accepts canonical ref strings."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    assert "skill:memory/retrieval" in registry
    assert "skill:missing/name" not in registry


def test_resource_registry_contains_rejects_other_types() -> None:
    """``__contains__`` returns False for non-ResourceId/non-str lookups."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    assert (42 in registry) is False
    assert (None in registry) is False
    assert ({"kind": "skill"} in registry) is False


def test_resource_registry_get_returns_resource_id_or_none() -> None:
    """``get`` returns the canonical ResourceId on hit, None on miss."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    # Hit by ResourceId
    assert registry.get(rid) == rid
    # Hit by canonical ref string
    assert registry.get("skill:memory/retrieval") == rid
    # Miss
    assert registry.get("skill:memory/missing") is None
    assert registry.get(ResourceId(kind="skill", namespace="memory", name="missing")) is None


def test_resource_registry_add_idempotent() -> None:
    """``add`` is idempotent on duplicate ref (no count growth, no error)."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry()
    registry.add(rid)
    registry.add(rid)
    registry.add(rid)
    assert len(registry) == 1
    assert rid in registry


# ---------------------------------------------------------------------------
# ResourceRegistry — merge semantics
# ---------------------------------------------------------------------------


def test_resource_registry_merge_unions() -> None:
    """``merge`` returns a new registry containing the union of two."""
    rid1 = ResourceId(kind="skill", namespace="memory", name="retrieval")
    rid2 = ResourceId(kind="prompt", namespace="coding_agent", name="system")
    rid3 = ResourceId(kind="role", namespace="assistants", name="solo")

    left = ResourceRegistry([rid1, rid2])
    right = ResourceRegistry([rid2, rid3])
    merged = left.merge(right)
    assert len(merged) == 3
    assert rid1 in merged
    assert rid2 in merged
    assert rid3 in merged


def test_resource_registry_merge_idempotent() -> None:
    """Merging a registry with itself yields the same set, no duplicates."""
    rid1 = ResourceId(kind="skill", namespace="memory", name="retrieval")
    rid2 = ResourceId(kind="prompt", namespace="coding_agent", name="system")
    registry = ResourceRegistry([rid1, rid2])
    merged = registry.merge(registry)
    assert len(merged) == 2
    assert merged.resources == registry.resources


def test_resource_registry_merge_does_not_mutate_inputs() -> None:
    """``merge`` returns a new registry; the originals are unchanged."""
    rid1 = ResourceId(kind="skill", namespace="memory", name="retrieval")
    rid2 = ResourceId(kind="prompt", namespace="coding_agent", name="system")
    rid3 = ResourceId(kind="role", namespace="assistants", name="solo")

    left = ResourceRegistry([rid1])
    right = ResourceRegistry([rid2, rid3])
    merged = left.merge(right)
    assert len(left) == 1
    assert len(right) == 2
    assert len(merged) == 3
    assert "merge" not in repr(left)
    # Sanity: left and right still have their original contents
    assert rid1 in left
    assert rid2 in right
    assert rid3 in right
    assert rid2 not in left
    assert rid1 not in right


# ---------------------------------------------------------------------------
# ResourceRegistry — output shape
# ---------------------------------------------------------------------------


def test_resource_registry_resources_property_sorted() -> None:
    """``resources`` property returns sorted, deduplicated tuple."""
    rid1 = ResourceId(kind="skill", namespace="memory", name="retrieval")
    rid2 = ResourceId(kind="skill", namespace="coding", name="refactor")
    rid3 = ResourceId(kind="prompt", namespace="coding_agent", name="system")
    registry = ResourceRegistry([rid3, rid2, rid1])
    out = registry.resources
    assert isinstance(out, tuple)
    assert [r.to_ref() for r in out] == [
        "prompt:coding_agent/system",
        "skill:coding/refactor",
        "skill:memory/retrieval",
    ]


def test_resource_registry_resources_property_returns_tuple() -> None:
    """``resources`` is a tuple (immutable, C8 + contracts purity)."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    registry = ResourceRegistry([rid])
    out = registry.resources
    assert isinstance(out, tuple)
    with pytest.raises((AttributeError, TypeError)):
        out[0] = rid  # type: ignore[index]


# ---------------------------------------------------------------------------
# Error type contract
# ---------------------------------------------------------------------------


def test_resource_projection_error_is_value_error() -> None:
    """``ResourceProjectionError`` is a ``ValueError`` (caller ergonomics)."""
    assert issubclass(ResourceProjectionError, ValueError)
    try:
        raise ResourceProjectionError("boom")
    except ValueError as exc:
        assert "boom" in str(exc)
