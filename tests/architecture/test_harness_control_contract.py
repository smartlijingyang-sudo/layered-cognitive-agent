"""Architecture guard for the harness/runtime control contract boundary."""

from __future__ import annotations

import ast
from pathlib import Path

from lca.contracts.protocols.control_verdict import ControlVerdict, ControlVerdictKind

REPO = Path(__file__).resolve().parents[2]
INTERPRETER = REPO / "lca" / "harness" / "declarative" / "interpreter.py"
PHASE_TRANSACTION = REPO / "lca" / "harness" / "declarative" / "phase_transaction.py"
# governance_verdicts.py was merged into phase_governance.py; the verdict
# contract lives in the same module that consumes it.
PHASE_GOVERNANCE = REPO / "lca" / "harness" / "declarative" / "phase_governance.py"
GOVERNANCE_VERDICTS = PHASE_GOVERNANCE
RETIRED_CONTROL_MODULES = (
    REPO / "lca" / "contracts" / "protocols" / "control_plan.py",
    REPO / "lca" / "harness" / "profile" / "control_plan_resolver.py",
    REPO / "lca" / "layer2_runtime" / "control_runtime.py",
)


def _imported_modules(path: Path) -> set[str]:
    """Read static imports without importing the module under test."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }


def test_control_contract_stays_in_harness_without_layer2_dependency() -> None:
    """Traversal and phase transactions consume only the shared control contract."""
    interpreter_imports = _imported_modules(INTERPRETER)
    transaction_imports = _imported_modules(PHASE_TRANSACTION)
    governance_imports = _imported_modules(PHASE_GOVERNANCE)
    verdict_imports = _imported_modules(GOVERNANCE_VERDICTS)

    assert "lca.layer2_runtime.control_runtime" not in interpreter_imports
    assert "lca.layer2_runtime.control_runtime" not in transaction_imports
    assert "lca.layer2_runtime.control_runtime" not in governance_imports
    assert "lca.layer2_runtime.control_runtime" not in verdict_imports
    assert "lca.contracts.protocols.control_verdict" in verdict_imports


def test_legacy_control_modules_remain_retired() -> None:
    """The executable plan must never regain a parallel ControlPlan path."""
    assert all(not path.exists() for path in RETIRED_CONTROL_MODULES)


def test_control_verdict_is_a_contract_value() -> None:
    """The shared value remains typed data, independent of runtime aggregation."""
    verdict = ControlVerdict(plugin_id="control.test", kind=ControlVerdictKind.ALLOW)

    assert verdict.kind is ControlVerdictKind.ALLOW
    assert verdict.plugin_id == "control.test"
