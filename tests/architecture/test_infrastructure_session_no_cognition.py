"""Structural tests: session context must not import cognition.

AGENTS.md §2.1 fixes the dependency direction ``contracts -> infrastructure ->
cognition -> runtime -> agent``. ``turn_control_reader`` sits in
infrastructure; the round-e refactor removed its upward imports of
``lca.cognition.convergence.payload`` and
``lca.cognition.brain.decision_gates.loop.fingerprint``. This test scans the
session/context package so a future change cannot silently reintroduce that
edge.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SESSION_CONTEXT = REPO / "lca" / "infrastructure" / "session" / "context"

_FORBIDDEN_UPWARD = (
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
)


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _import_statements(text: str) -> list[str]:
    """Extract dotted import targets from ``import x`` / ``from x import ...``."""
    targets: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("import "):
            targets.append(line[len("import ") :].split(" as ")[0])
        elif line.startswith("from "):
            target = line[len("from ") :].split(" import ")[0]
            targets.append(target)
    return targets


def test_session_context_has_no_upward_imports() -> None:
    violations: list[str] = []
    for path in _py_files(SESSION_CONTEXT):
        text = path.read_text(encoding="utf-8")
        for target in _import_statements(text):
            if any(
                target == prefix or target.startswith(prefix + ".") for prefix in _FORBIDDEN_UPWARD
            ):
                violations.append(f"{path}: {target}")
    assert violations == [], f"upward imports in infrastructure/session/context: {violations}"


def test_turn_control_reader_source_has_no_cognition_imports() -> None:
    """The specific file from the round-e inventory must stay clean."""
    path = SESSION_CONTEXT / "turn_control_reader.py"
    source = path.read_text(encoding="utf-8")
    assert "lca.cognition" not in source, (
        "turn_control_reader.py must not import cognition (inject callbacks / "
        "use contracts instead)"
    )
