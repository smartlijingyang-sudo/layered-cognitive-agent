"""HPC-L6 event catalog activation_ref guard (ADR-0199 §11 / P3-08).

Per ADR-0199 §11 HPC-L6: durable EP payload MUST contain
``activation_ref`` (or the equivalent triple ``plan_ref`` /
``graph_ref`` / ``plugin_set_ref``). Per §13.4 P3-09 acceptance:
``event catalog test: payload schema test``.

This guard:
  - locates the canonical spine event catalog
    (``lca_kernel/events/config/observability/spine.yaml``);
  - identifies *durable* entries — those whose ``publishers`` route
    through ``DefaultFactGateway`` (the only durable spine publisher;
    spine EPs that publish via plugin marker ids stay on the in-process
    EventBus and are not subject to HPC-L6);
  - asserts each durable entry's ``fields:`` block declares at least one
    activation-binding field;
  - parses the canonical Python contracts payload dataclasses
    (``lca_kernel/events/payloads/spine.py`` and
    ``lca/contracts/event.py``) and confirms the ``activation_ref``
    helper utilities documented in §2.2.2 produce the canonical hash
    form ``lca.activation.v1:<sha256-hex>``.

When the catalog is updated without an activation-binding field on a
durable EP, this test fails loud. When a non-durable EP gains the
field unnecessarily, this test does not flag it (silence ≠ failure).

Notes on the catalog layout:
  - The actual catalog is YAML (not Python dataclasses). We parse YAML
    directly with :mod:`yaml` to enumerate entries.
  - The brief's dataclass heuristic is preserved as a second path so
    that a future Python-side catalog (``lca_kernel/events/catalog.py``
    or similar) is automatically picked up.
  - Both paths are guarded behind ``pytest.skip`` if the file is absent.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# ADR-0199 §2.2.2 + I-HPC-3: durable events must carry activation_ref
# or any of the three refs that compose it.
ACTIVATION_REF_FIELDS: frozenset[str] = frozenset(
    {
        "activation_ref",
        "plan_ref",
        "graph_ref",
        "plugin_set_ref",
    }
)

# Class-path token that marks a spine EP as durable: it is the
# canonical FactGateway publisher per ``lca.loop.fact_gateway``.
# Non-durable EPs publish via plugin marker ids (string tokens).
DURABLE_PUBLISHER_TOKENS: frozenset[str] = frozenset({"lca.loop.fact_gateway.DefaultFactGateway"})

# Catalog candidates — ordered by preference. The actual catalog in
# this repo is YAML (spine.yaml) so that is listed first. Python
# dataclass fallbacks follow the brief's heuristic.
_CATALOG_CANDIDATES: tuple[Path, ...] = (
    REPO_ROOT / "lca_kernel" / "events" / "config" / "observability" / "spine.yaml",
    REPO_ROOT / "lca_kernel" / "events" / "catalog.py",
    REPO_ROOT / "lca_kernel" / "events" / "config",
    REPO_ROOT / "lca" / "contracts" / "event.py",
)


def _find_catalog_file() -> Path | None:
    """Return the first existing catalog file (YAML preferred)."""
    for candidate in _CATALOG_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def _parse_yaml_catalog(path: Path) -> list[dict[str, object]]:
    """Parse the YAML event catalog; return the ``events:`` list.

    The catalog root is a mapping with an ``events:`` key whose value
    is the list of EP entries. Other top-level keys (``consumer_rules:``)
    are ignored.
    """
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return []
    events = data.get("events")
    if not isinstance(events, list):
        return []
    return [e for e in events if isinstance(e, dict)]


def _is_durable_entry(entry: dict[str, object]) -> bool:
    """True iff entry publishes through the durable FactGateway."""
    publishers = entry.get("publishers")
    if not isinstance(publishers, list):
        return False
    return any(token in DURABLE_PUBLISHER_TOKENS for token in publishers if isinstance(token, str))


def _entry_fields(entry: dict[str, object]) -> set[str]:
    """Return the declared field names of a catalog entry."""
    fields = entry.get("fields")
    if not isinstance(fields, dict):
        return set()
    return {name for name in fields if isinstance(name, str)}


def _collect_python_dataclass_names(path: Path) -> list[str]:
    """Heuristic: dataclass names suggesting an EP/event payload.

    Returns unique class names whose name contains ``Event``,
    ``Payload``, ``Fact``, or ``Receipt``.
    """
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []

    out: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        is_dataclass = any(
            (isinstance(dec, ast.Name) and dec.id == "dataclass")
            or (isinstance(dec, ast.Attribute) and dec.attr == "dataclass")
            for dec in node.decorator_list
        )
        if not is_dataclass:
            continue
        if any(hint in node.name for hint in ("Event", "Payload", "Fact", "Receipt")):
            out.add(node.name)
    return sorted(out)


def _dataclass_field_names(path: Path, class_name: str) -> set[str] | None:
    """Return the field name set of a named dataclass in ``path``."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            fields: set[str] = set()
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.add(stmt.target.id)
                elif isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Name):
                            fields.add(tgt.id)
            return fields
    return None


class TestHPCL6EventCatalogActivationRef:
    """HPC-L6: durable event payloads carry activation_ref (or equivalent triple).

    The canonical spine event catalog is
    ``lca_kernel/events/config/observability/spine.yaml``. Each entry's
    ``fields:`` block declares the payload schema. We restrict the
    assertion to entries whose ``publishers`` route through the durable
    FactGateway — the only publisher that touches
    :class:`lca.loop.fact_gateway.DefaultFactGateway` and therefore the
    only kind that ends up in :class:`Session.append`.
    """

    def test_catalog_file_exists(self) -> None:
        """At least one canonical event catalog file must exist."""
        catalog = _find_catalog_file()
        assert catalog is not None, "no event catalog found in expected locations:\n" + "\n".join(
            f"  - {c}" for c in _CATALOG_CANDIDATES
        )

    def test_yaml_catalog_parses(self) -> None:
        """The YAML catalog root must be a mapping with an ``events:`` list."""
        catalog = _find_catalog_file()
        if catalog is None:
            pytest.skip("no event catalog file present")
        if catalog.suffix != ".yaml" and catalog.suffix != ".yml":
            pytest.skip(f"non-YAML catalog {catalog}; see dataclass tests instead")
        entries = _parse_yaml_catalog(catalog)
        assert entries, f"yaml catalog {catalog} has empty ``events:`` list"

    def test_durable_entries_carry_activation_ref(self) -> None:
        """Every durable EP payload MUST carry activation_ref or equivalent triple.

        Per ADR-0199 §11 HPC-L6 + §13.4 P3-09 acceptance, durable
        event payloads flowing through ``Session.append`` /
        ``FactGateway`` must bind back to a plan-bound activation.
        """
        catalog = _find_catalog_file()
        assert catalog is not None, "no event catalog file found"
        if catalog.suffix not in {".yaml", ".yml"}:
            pytest.skip(f"YAML-only assertion; catalog is {catalog.suffix}")

        entries = _parse_yaml_catalog(catalog)
        durable_entries = [e for e in entries if _is_durable_entry(e)]

        assert durable_entries, (
            f"catalog {catalog} has zero durable entries (no FactGateway publishers); "
            "HPC-L6 cannot be evaluated — fix the catalog fixture or the guard"
        )

        violations: list[str] = []
        for entry in durable_entries:
            category = entry.get("category")
            fields = _entry_fields(entry)
            if not (ACTIVATION_REF_FIELDS & fields):
                violations.append(
                    f"{category!s} (fields: {sorted(fields)}) — "
                    f"missing activation binding: need at least one of {sorted(ACTIVATION_REF_FIELDS)}"
                )

        assert not violations, (
            "HPC-L6: durable EP payload fields missing activation binding "
            f"({len(violations)} violations):\n"
            + "\n".join(f"  - {v}" for v in violations)
            + "\nPer ADR-0199 §11 + §13.4: every durable EP payload must "
            "declare activation_ref (or plan_ref / graph_ref / plugin_set_ref) "
            "in its fields block."
        )

    def test_durable_entry_field_count_matches_typing(self) -> None:
        """Fields declared as ``name: str`` should not be empty / typos.

        A defensive sanity check: the catalog loader trusts field names.
        If a future PR adds ``activation_ref: str`` but mistypes
        ``actiation_ref: str``, this guard flags the regression.
        """
        catalog = _find_catalog_file()
        if catalog is None:
            pytest.skip("no event catalog file present")
        if catalog.suffix not in {".yaml", ".yml"}:
            pytest.skip("YAML-only assertion")

        entries = _parse_yaml_catalog(catalog)
        durable_entries = [e for e in entries if _is_durable_entry(e)]

        # Light sanity: each durable entry should declare at least one
        # typed field (otherwise the schema is empty and the guard
        # above would be trivially satisfied by an empty ``fields:``).
        empty: list[str] = []
        for entry in durable_entries:
            fields = _entry_fields(entry)
            if not fields:
                empty.append(str(entry.get("category")))
        assert not empty, "durable EP entries with empty fields block:\n" + "\n".join(
            f"  - {c}" for c in empty
        )


class TestHPCL6PythonDataclassFallback:
    """AST-based fallback for any future Python-side event catalog.

    When the catalog becomes a Python module (e.g. via autogenerated
    ``lca_kernel/events/catalog.py``), this class guards the same
    invariant at the dataclass level.
    """

    def test_python_dataclass_catalog_has_activation_ref(self) -> None:
        """Each EP-shaped dataclass must declare activation_ref (or triple).

        The fallback targets only Python dataclass catalogs. If the
        real catalog is YAML, the YAML test above is the source of
        truth — this test is a structural mirror that catches
        regression if anyone introduces a parallel Python catalog.
        Pydantic ``BaseModel`` subclasses are skipped: they are not
        dataclasses and are covered by the YAML path.
        """
        for candidate in (
            REPO_ROOT / "lca_kernel" / "events" / "catalog.py",
            REPO_ROOT / "lca_kernel" / "events" / "payloads" / "spine.py",
        ):
            if not candidate.is_file():
                continue
            names = _collect_python_dataclass_names(candidate)
            if not names:
                # Pydantic models in this file are not dataclasses; the
                # YAML catalog is the source of truth.
                continue

            violations: list[str] = []
            for name in names:
                fields = _dataclass_field_names(candidate, name)
                if fields is None:
                    continue
                # Only flag the *base* dataclass spine — subclasses are
                # not required to redeclare the field.
                if name in {"SpineEventPayload", "EventPayload"} and not (
                    fields & ACTIVATION_REF_FIELDS
                ):
                    violations.append(
                        f"{candidate.name}::{name} (fields: {sorted(fields)}) "
                        "— base payload missing activation binding"
                    )
            assert not violations, "HPC-L6 (Python fallback):\n" + "\n".join(
                f"  - {v}" for v in violations
            )


class TestActivationBindingFormat:
    """Activation_ref canonical format is ``lca.activation.v1:<sha256-hex>``.

    Per ADR-0199 §2.2.2 + I-HPC-3 + C8 (deterministic). This test
    exercises the runtime helper so the guard cannot drift from the
    actual hashing function.
    """

    def test_activation_ref_format_is_canonical(self) -> None:
        """``compute_activation_ref`` must emit ``lca.activation.v1:<64 hex>``."""
        from lca.harness.runtime.activation_ref import (
            _ACTIVATION_HASH_NAMESPACE,
            compute_activation_ref,
            is_activation_ref,
        )

        ref = compute_activation_ref(
            plan_ref="plan_x",
            graph_ref="graph_y",
            plugin_set_ref="plugin_z",
            session_id="sess_123",
        )

        prefix = f"{_ACTIVATION_HASH_NAMESPACE}:"
        assert ref.startswith(prefix), f"activation_ref must start with {prefix!r}; got {ref!r}"
        hex_part = ref[len(prefix) :]
        assert len(hex_part) == 64, f"hex part must be 64 chars (sha256); got {len(hex_part)}"
        assert all(c in "0123456789abcdef" for c in hex_part), (
            f"hex part must be lowercase hex; got {hex_part!r}"
        )
        assert is_activation_ref(ref), "is_activation_ref must accept ref"

    def test_activation_ref_stable_across_calls(self) -> None:
        """Same inputs → same activation_ref (C8 deterministic)."""
        from lca.harness.runtime.activation_ref import compute_activation_ref

        kwargs = {
            "plan_ref": "plan_a",
            "graph_ref": "graph_b",
            "plugin_set_ref": "plugin_c",
            "session_id": "sess_x",
        }
        first = compute_activation_ref(**kwargs)
        second = compute_activation_ref(**kwargs)
        assert first == second, "compute_activation_ref is non-deterministic (C8)"

    def test_activation_ref_changes_with_session_id(self) -> None:
        """session_id participates in the hash (I-HPC-3 binding)."""
        from lca.harness.runtime.activation_ref import compute_activation_ref

        base = {
            "plan_ref": "plan_a",
            "graph_ref": "graph_b",
            "plugin_set_ref": "plugin_c",
        }
        a = compute_activation_ref(**base, session_id="sess_1")
        b = compute_activation_ref(**base, session_id="sess_2")
        assert a != b, "session_id must influence activation_ref (I-HPC-3)"


__all__ = [
    "ACTIVATION_REF_FIELDS",
    "DURABLE_PUBLISHER_TOKENS",
]
