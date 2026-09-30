"""Structural tests: harness no longer owns observability assembly.

The assembly functions moved from ``lca.harness.observability`` (which
violated harness-depends-only-on-contracts) into
``lca_kernel.runtime.observability`` where the kernel composition boundary
lives.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_harness_observability_module_is_gone() -> None:
    assert not (REPO / "lca" / "harness" / "observability").exists()


def test_kernel_observability_exports_assembly_functions() -> None:
    from lca_kernel.runtime.observability import (
        assemble_observability,
        default_policy,
        make_minimal_bound,
    )

    assert callable(assemble_observability)
    assert callable(default_policy)
    assert callable(make_minimal_bound)


def test_harness_has_no_infrastructure_import_in_observability() -> None:
    """No module may import the retired harness observability assembly."""
    import re

    violations: list[str] = []
    for path in (REPO / "lca").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"from lca\.harness\.observability import", text):
            violations.append(str(path))
    assert violations == [], f"harness observability still imported: {violations}"
