"""Structural tests: cognition must not import runtime (AGENTS.md §2.1).

The dependency direction is ``contracts -> infrastructure -> cognition ->
runtime -> agent``. Cognition needing the model-visible history uses the
``lca.infrastructure.session.history`` seam; it must never import the concrete
``lca.runtime.session.run_session_writer`` at runtime.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COGNITION = REPO / "lca" / "cognition"


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_cognition_has_no_runtime_imports() -> None:
    violations: list[str] = []
    for path in _py_files(COGNITION):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        in_type_checking = False
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "if TYPE_CHECKING:":
                in_type_checking = True
                continue
            if in_type_checking:
                # Leaving the TYPE_CHECKING block: a non-indented line ends
                # it. TYPE_CHECKING bodies use 4-space indentation; blank lines
                # stay inside.
                indent = len(line) - len(line.lstrip())
                if stripped and indent <= 0:
                    in_type_checking = False
                else:
                    continue
            if stripped.startswith("from lca.runtime") or stripped.startswith("import lca.runtime"):
                violations.append(f"{path}:{index + 1}: {stripped}")
    assert violations == [], f"cognition imports runtime at runtime: {violations}"


def test_llm_turn_executor_uses_history_seam() -> None:
    import lca.cognition.brain.llm_turn.executor as executor

    source = Path(executor.__file__).read_text(encoding="utf-8")
    assert "lca.infrastructure.session.history" in source
    assert "RunSessionWriter" not in source
