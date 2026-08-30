"""Architecture guards for the declarative phase-observation seam."""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TRANSACTION = REPO / "lca" / "harness" / "declarative" / "phase_transaction.py"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }


def test_phase_transaction_depends_on_observation_seam_not_tracing_backend() -> None:
    """Span selection belongs to the observer adapter, not phase execution."""
    imports = _imported_modules(TRANSACTION)

    assert "lca.harness.declarative.phase_observation" in imports
    assert "lca.layer0_infra.observability" not in imports
    assert "lca.contracts.atoms.telemetry" not in imports
