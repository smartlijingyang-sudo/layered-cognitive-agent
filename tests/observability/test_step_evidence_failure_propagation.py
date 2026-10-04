"""INV-06: Test step evidence failure propagation and dynamic conclusion synthesis.

Validates that:
1. Failed tool execution produces non-zero exit_code in StepEvidence.
2. Conclusion reflects the actual non-zero exit code and root cause error.
3. Real stderr is surfaced in StepEvidence without fabrication.
"""

from __future__ import annotations

from lca.contracts.models.observability.activity import parse_step_evidence


def test_step_evidence_failure_propagation_with_exit_code_and_stderr() -> None:
    """Tool failure must dynamically produce exit_code, stderr, and failure conclusion."""
    ev = parse_step_evidence(
        tool_name="bash",
        arguments={"command": "cat non_existent_file.txt"},
        tool_result={
            "ok": False,
            "exit_code": 2,
            "latency_ms": 42,
            "error": "Command failed with exit code 2",
            "stderr": "cat: non_existent_file.txt: No such file or directory",
        },
        thinking={"reasoning": "Attempting to inspect non_existent_file.txt"},
        step_id="step-002",
    )

    assert ev.exit_code == 2
    assert ev.duration_ms == 42
    assert ev.conclusion is not None
    assert "退出码 2" in ev.conclusion
    assert "Command failed with exit code 2" in ev.conclusion or "No such file" in ev.conclusion

    # Stderr snippet must be present
    has_stderr_snippet = any(
        "No such file or directory" in snippet.get("code", "") for snippet in ev.code_snippets
    )
    assert has_stderr_snippet, f"Expected stderr snippet in code_snippets: {ev.code_snippets}"
