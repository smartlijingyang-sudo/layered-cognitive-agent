"""INV-04: Test zero hardcoding in activity evidence generation.

Validates that:
1. AST scan of `activity.py` contains:
   - ZERO `3841` magic numbers.
   - ZERO `ZZSTART` string literals.
   - ZERO `pytest 9.0.1` fake outputs.
   - ZERO `asst_3dacffc01a90` hardcoded assistant IDs.
2. `parse_step_evidence` never fabricates fake output when stdout is empty.
"""

from __future__ import annotations

import ast
from pathlib import Path

import lca.contracts.models.observability.activity as activity_module
from lca.contracts.models.observability.activity import parse_step_evidence


def test_activity_module_ast_has_zero_hardcoded_magics() -> None:
    """AST check: ensure 3841, ZZSTART, fake pytest, and hardcoded assistant ID are eliminated."""
    module_path = Path(activity_module.__file__)
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            val = node.value
            if isinstance(val, (int, float)):
                assert val != 3841, "Found forbidden magic number 3841 in activity.py"
            elif isinstance(val, str):
                assert "ZZSTART" not in val, (
                    f"Found forbidden marker 'ZZSTART' in activity.py: {val!r}"
                )
                assert "pytest 9.0.1" not in val, (
                    f"Found forbidden fake output 'pytest 9.0.1' in activity.py: {val!r}"
                )
                assert "asst_3dacffc01a90" not in val, (
                    f"Found forbidden assistant ID 'asst_3dacffc01a90' in activity.py: {val!r}"
                )


def test_parse_step_evidence_zero_fabrication_on_empty_result() -> None:
    """When a tool produces empty output, parse_step_evidence must not fabricate mock pytest or soul."""
    ev = parse_step_evidence(
        tool_name="bash",
        arguments={"command": "pytest --version"},
        tool_result={"ok": True, "latency_ms": 50, "stdout_head": ""},
        thinking={},
        step_id="step-001",
    )
    # Must not fabricate fake pytest 9.0.1
    for snippet in ev.code_snippets:
        assert "pytest 9.0.1" not in snippet.get("code", "")
    assert ev.duration_ms == 50
    assert ev.exit_code == 0
    assert ev.truncated_boundary == ""
