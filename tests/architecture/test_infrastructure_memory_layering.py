"""Structural tests: infrastructure must not import cognition.

AGENTS.md §2.1 fixes the dependency direction ``contracts -> infrastructure ->
cognition -> runtime -> agent``. These tests scan the infrastructure memory
package for upward imports so a future refactor cannot silently reintroduce
the ``standing_refresh -> cognition`` edge that round 5 removed.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INFRA_MEMORY = REPO / "lca" / "infrastructure" / "memory"

_FORBIDDEN_UPWARD = (
    "lca.cognition",
    "lca.runtime",
    "lca.agent",
    "lca.application",
    "lca.harness",
    "lca.plugins",
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


def test_infrastructure_memory_has_no_upward_imports() -> None:
    violations: list[str] = []
    for path in _py_files(INFRA_MEMORY):
        text = path.read_text(encoding="utf-8")
        for target in _import_statements(text):
            if any(
                target == prefix or target.startswith(prefix + ".") for prefix in _FORBIDDEN_UPWARD
            ):
                violations.append(f"{path}: {target}")
    assert violations == [], f"upward imports in infrastructure/memory: {violations}"


def test_no_local_standing_module_remains_in_cognition() -> None:
    old_path = REPO / "lca" / "cognition" / "memory" / "standing.py"
    assert not old_path.exists(), "standing module must live in infrastructure now"


def test_contextfiles_package_does_not_import_the_host() -> None:
    """The package must stay movable. It may import only itself."""

    root = REPO / "lca" / "infrastructure" / "memory" / "contextfiles"
    allowed = "lca.infrastructure.memory.contextfiles"
    violations: list[str] = []
    for path in _py_files(root):
        text = path.read_text(encoding="utf-8")
        for target in _import_statements(text):
            if target.startswith("lca.") and not (
                target == allowed or target.startswith(allowed + ".")
            ):
                violations.append(f"{path}: {target}")
    assert violations == [], f"host imports inside contextfiles: {violations}"


def test_cognition_memory_imports_down_for_standing() -> None:
    """Cognition may import the standing helpers from infrastructure (downward)."""
    import lca.cognition.memory  # noqa: F401

    # The persona plugin and the refresh loader both resolve from infrastructure.
    from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
    from lca.infrastructure.memory.contextfiles.domain.standing import assemble_standing

    assert "SOUL.md" in packaged_layout().standing_files
    assert callable(assemble_standing)
