"""Architecture guards for the declarative phase-observation seam."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PHASE_OBSERVATION = REPO / "lca" / "harness" / "declarative" / "lifecycle" / "phase_observation.py"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }


def test_phase_observation_seam_depends_on_contracts_not_tracing_backend() -> None:
    """Span selection belongs to the injected observer, not harness code."""
    imports = _imported_modules(PHASE_OBSERVATION)

    assert "lca.contracts.protocols.journal.phase.observation" in imports
    assert "lca.contracts.protocols.telemetry.span_opener" in imports
    assert "lca.infrastructure.observability" not in imports


def test_legacy_loop_transaction_module_is_retired() -> None:
    """The pre-kernel phase transaction module no longer exists."""
    assert not (REPO / "lca" / "loop" / "transaction.py").exists()


def test_no_live_reference_to_legacy_transaction_module() -> None:
    """No Python file may import or read the retired transaction module."""
    import re

    violations: list[str] = []
    for root in ("lca", "lca_kernel", "tests"):
        for path in (REPO / root).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if re.search(r"lca\.loop\.transaction", text):
                violations.append(str(path))
    assert violations == [], f"legacy transaction module still referenced: {violations}"
