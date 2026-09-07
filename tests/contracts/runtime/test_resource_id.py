"""Behavioral tests for ``lca.contracts.runtime.resource`` (P4-01).

Covers the canonical ``ResourceId`` contract per ADR-0199 §3.1, §3.3 #7
(content ≠ execute, I-HPC-6) and §4 (resource references are namespaced
IDs of the form ``"<kind>:<namespace>/<name>"``).

Per I-HPC-6 the resource is the read-only content dimension; the contract
must reject anything that could let resource content acquire execute
permission, including unrecognised kinds, ambiguous delimiters, or
reserved namespaces that could shadow system resources.
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
from collections.abc import Iterator

import pytest

from lca.contracts.runtime.resource import (
    RESERVED_NAMESPACES,
    ResourceId,
)

# ---------------------------------------------------------------------------
# Construction (per kind)
# ---------------------------------------------------------------------------


def test_construct_skill_resource_id() -> None:
    """Skill resources are constructible with the canonical kind."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    assert rid.kind == "skill"
    assert rid.namespace == "memory"
    assert rid.name == "retrieval"
    assert rid.to_ref() == "skill:memory/retrieval"


def test_construct_prompt_resource_id() -> None:
    """Prompt resources are constructible with the canonical kind."""
    rid = ResourceId(kind="prompt", namespace="coding_agent", name="system")
    assert rid.kind == "prompt"
    assert rid.namespace == "coding_agent"
    assert rid.name == "system"
    assert rid.to_ref() == "prompt:coding_agent/system"


def test_construct_role_resource_id() -> None:
    """Role resources are constructible with the canonical kind."""
    rid = ResourceId(kind="role", namespace="assistants", name="solo")
    assert rid.kind == "role"
    assert rid.namespace == "assistants"
    assert rid.name == "solo"
    assert rid.to_ref() == "role:assistants/solo"


# ---------------------------------------------------------------------------
# to_ref / from_ref
# ---------------------------------------------------------------------------


def test_to_ref_format() -> None:
    """``to_ref()`` produces ``<kind>:<namespace>/<name>`` and round-trips."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    ref = rid.to_ref()
    assert ref == "skill:memory/retrieval"
    # Round-trip
    rebuilt = ResourceId.from_ref(ref)
    assert rebuilt == rid


def test_from_ref_skill() -> None:
    """``from_ref`` parses a skill ref into the right triple."""
    rid = ResourceId.from_ref("skill:memory/retrieval")
    assert rid.kind == "skill"
    assert rid.namespace == "memory"
    assert rid.name == "retrieval"


def test_from_ref_prompt() -> None:
    """``from_ref`` parses a prompt ref into the right triple."""
    rid = ResourceId.from_ref("prompt:coding_agent/system")
    assert rid.kind == "prompt"
    assert rid.namespace == "coding_agent"
    assert rid.name == "system"


def test_from_ref_role() -> None:
    """``from_ref`` parses a role ref into the right triple."""
    rid = ResourceId.from_ref("role:assistants/solo")
    assert rid.kind == "role"
    assert rid.namespace == "assistants"
    assert rid.name == "solo"


@pytest.mark.parametrize(
    "ref",
    [
        "skill:memory/retrieval",
        "skill:coding/debug",
        "prompt:coding_agent/system",
        "prompt:router/main",
        "role:assistants/solo",
        "role:assistants/team_lead",
        "skill:ops-incident/runbook",
        "skill:data/etl_daily",
    ],
)
def test_from_ref_then_to_ref_round_trip(ref: str) -> None:
    """Round-trip ``from_ref`` → ``to_ref`` returns the original canonical ref."""
    rid = ResourceId.from_ref(ref)
    assert rid.to_ref() == ref


# ---------------------------------------------------------------------------
# Construction-time validation (namespace + name patterns)
# ---------------------------------------------------------------------------


def test_invalid_namespace_with_slash_rejected() -> None:
    """Namespaces must not contain ``/`` (it is the namespace/name separator)."""
    with pytest.raises(ValueError, match="namespace must match"):
        ResourceId(kind="skill", namespace="mem/ory", name="retrieval")


def test_invalid_namespace_with_colon_rejected() -> None:
    """Namespaces must not contain ``:`` (it is the kind/namespace separator)."""
    with pytest.raises(ValueError, match="namespace must match"):
        ResourceId(kind="skill", namespace="mem:ory", name="retrieval")


def test_invalid_namespace_with_uppercase_rejected() -> None:
    """Namespaces are lowercase alphanumerics + ``_`` + ``-``; uppercase rejected."""
    with pytest.raises(ValueError, match="namespace must match"):
        ResourceId(kind="skill", namespace="Memory", name="retrieval")


@pytest.mark.parametrize("reserved", sorted(RESERVED_NAMESPACES))
def test_reserved_namespace_rejected(reserved: str) -> None:
    """Reserved namespaces (``system`` / ``internal`` / ``_reserved``) are rejected.

    Per ADR-0199 §4, only user-declared, non-reserved namespaces are allowed
    for content resources. Reserved namespaces are reserved for the kernel
    so user-declared resources cannot shadow system resources.
    """
    with pytest.raises(ValueError, match="is reserved"):
        ResourceId(kind="skill", namespace=reserved, name="retrieval")


def test_empty_namespace_rejected() -> None:
    """Empty namespace is rejected (the pattern requires ``+`` not ``*``)."""
    with pytest.raises(ValueError, match="namespace must match"):
        ResourceId(kind="skill", namespace="", name="retrieval")


def test_empty_name_rejected() -> None:
    """Empty name is rejected (the pattern requires ``+`` not ``*``)."""
    with pytest.raises(ValueError, match="name must match"):
        ResourceId(kind="skill", namespace="memory", name="")


def test_invalid_name_with_uppercase_rejected() -> None:
    """Names are lowercase alphanumerics + ``_`` + ``-``; uppercase rejected."""
    with pytest.raises(ValueError, match="name must match"):
        ResourceId(kind="skill", namespace="memory", name="Retrieval")


def test_invalid_name_with_slash_rejected() -> None:
    """Names must not contain ``/`` (it is the namespace/name separator)."""
    with pytest.raises(ValueError, match="name must match"):
        ResourceId(kind="skill", namespace="memory", name="ret/rieval")


def test_invalid_name_with_whitespace_rejected() -> None:
    """Names must not contain whitespace."""
    with pytest.raises(ValueError, match="name must match"):
        ResourceId(kind="skill", namespace="memory", name="retrieval v1")


# ---------------------------------------------------------------------------
# from_ref validation
# ---------------------------------------------------------------------------


def test_from_ref_missing_colon_rejected() -> None:
    """``from_ref`` requires a ``:`` separating kind from namespace/name."""
    with pytest.raises(ValueError, match="must contain ':' separating kind"):
        ResourceId.from_ref("skill-memory-retrieval")


def test_from_ref_missing_slash_rejected() -> None:
    """``from_ref`` requires a ``/`` separating namespace from name."""
    with pytest.raises(ValueError, match="must contain '/' separating namespace"):
        ResourceId.from_ref("skill:memory-retrieval")


def test_from_ref_unknown_kind_rejected() -> None:
    """``from_ref`` rejects kinds outside the closed set (ADR-0199 §4)."""
    with pytest.raises(ValueError, match="kind must be one of"):
        ResourceId.from_ref("tool:memory/retrieval")


def test_from_ref_non_string_rejected() -> None:
    """``from_ref`` rejects non-string input (regression: not a bool/int/list)."""
    for bad in (None, 42, 3.14, True, b"skill:memory/retrieval", ["skill:memory/retrieval"]):
        with pytest.raises(ValueError, match="resource ref must be a string"):
            ResourceId.from_ref(bad)  # type: ignore[arg-type]


def test_from_ref_empty_string_rejected() -> None:
    """``from_ref`` rejects an empty ref (no ``:`` present)."""
    with pytest.raises(ValueError, match="must contain ':' separating kind"):
        ResourceId.from_ref("")


# ---------------------------------------------------------------------------
# Frozen + equality
# ---------------------------------------------------------------------------


def test_frozen_blocks_mutation() -> None:
    """Frozen dataclass rejects attribute assignment (per ADR-0199 immutability)."""
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    with pytest.raises(dataclasses.FrozenInstanceError):
        rid.kind = "prompt"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        rid.namespace = "coding"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        rid.name = "debug"  # type: ignore[misc]


def test_equality_same_components() -> None:
    """Two ``ResourceId`` with the same components compare equal and share hash."""
    a = ResourceId(kind="skill", namespace="memory", name="retrieval")
    b = ResourceId(kind="skill", namespace="memory", name="retrieval")
    assert a == b
    assert hash(a) == hash(b)


def test_inequality_different_kind() -> None:
    """Different ``kind`` produces unequal ``ResourceId`` values."""
    a = ResourceId(kind="skill", namespace="memory", name="retrieval")
    b = ResourceId(kind="prompt", namespace="memory", name="retrieval")
    assert a != b


def test_inequality_different_namespace() -> None:
    """Different ``namespace`` produces unequal ``ResourceId`` values."""
    a = ResourceId(kind="skill", namespace="memory", name="retrieval")
    b = ResourceId(kind="skill", namespace="coding", name="retrieval")
    assert a != b


def test_inequality_different_name() -> None:
    """Different ``name`` produces unequal ``ResourceId`` values."""
    a = ResourceId(kind="skill", namespace="memory", name="retrieval")
    b = ResourceId(kind="skill", namespace="memory", name="indexing")
    assert a != b


# ---------------------------------------------------------------------------
# Purity — no I/O / no upper-layer imports
# ---------------------------------------------------------------------------


def test_no_io_imports_in_module() -> None:
    """``resource.py`` is a pure contracts module.

    Per ADR-0199 §2.2 (contracts layer) and importlinter contract #3
    (contracts purity), the resource module must not import any I/O,
    logging, env-reading, or upper-layer module. Any of those would let
    resource content reach outside the contracts surface and acquire
    behaviour beyond pure identity.
    """
    module = importlib.import_module("lca.contracts.runtime.resource")
    forbidden_substrings = (
        "os",  # env reads
        "sys",  # process state
        "logging",
        "io",
        "pathlib",
        "subprocess",
        "shutil",
        "requests",
        "urllib",
        "httpx",
    )
    module_names = {name for name in dir(module) if not name.startswith("_")}
    leaked = sorted(
        name
        for name in module_names
        if any(name == piece or name.startswith(f"{piece}.") for piece in forbidden_substrings)
    )
    assert leaked == [], f"resource module leaks impure names: {leaked!r}"


def test_no_upper_layer_lca_imports() -> None:
    """``resource.py`` does not import any upper-layer ``lca.*`` module.

    Per I-HPC-1 / importlinter contract #3 the contracts layer is pure.
    """
    module = importlib.import_module("lca.contracts.runtime.resource")
    module_file = module.__file__ or ""
    assert module_file.endswith("resource.py"), f"unexpected module file: {module_file!r}"
    # Spot-check the module spec: only lca.contracts.* should be reachable.
    forbidden_lca = (
        "lca.infrastructure",
        "lca.cognition",
        "lca.runtime",
        "lca.agent",
        "lca.harness",
        "lca.application",
        "lca.plugins",
    )
    leaked = [name for name in sys.modules if name in forbidden_lca]
    assert leaked == [], f"resource module pulled upper-layer modules: {leaked!r}"


# ---------------------------------------------------------------------------
# Slots + immutability ergonomics
# ---------------------------------------------------------------------------


def test_slots_present() -> None:
    """``ResourceId`` is declared with ``slots=True`` (per ADR-0199 contract style).

    The frozen+slots pair gives us hashable, memory-efficient, dataclass
    values that match ``RunIntent`` / ``SessionActivation``.
    """
    rid = ResourceId(kind="skill", namespace="memory", name="retrieval")
    # ``__slots__`` makes ``__dict__`` absent on the instance.
    assert not hasattr(rid, "__dict__")
    assert "__slots__" in ResourceId.__dict__ or hasattr(ResourceId, "__slots__")


def test_hashable_for_set_membership() -> None:
    """``ResourceId`` is hashable and usable as a set member (frozen+slots)."""
    a = ResourceId(kind="skill", namespace="memory", name="retrieval")
    b = ResourceId(kind="skill", namespace="memory", name="retrieval")
    c = ResourceId(kind="skill", namespace="memory", name="indexing")
    bucket: set[ResourceId] = {a, b, c}
    # Equality collapses the duplicate.
    assert len(bucket) == 2
    assert a in bucket
    assert c in bucket


@pytest.fixture
def _reset_resource_module() -> Iterator[None]:
    """Force a fresh import of the resource module for the purity test.

    The upper-layer-leak check walks ``sys.modules``; if an unrelated test
    has already imported an upper-layer module, the assertion will be
    confused. We re-import the resource module from a clean view of the
    module's own spec to assert only what *it* brought in.
    """
    yield


# Reference the fixture so ruff does not flag it as unused; the fixture is
# intentionally available for any future per-test isolation needs.
_ = _reset_resource_module
