from __future__ import annotations

from lca.plugins.session.derivers.step_tree.journal_fold import fold_step_tree


def test_fold_concurrent_tools_preserves_all_calls_and_deliverables() -> None:
    events = [
        {"execution_point": "llm.request.header", "payload": {"step_id": "step-001"}, "when": 1},
        # Tool 1: export PDF
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "exportFile",
                "invocation_id": "inv_pdf",
                "arguments": {"path": "/mnt/data/report.pdf"},
            },
            "when": 2,
        },
        # Tool 2: export chart 1
        {
            "execution_point": "step.tool_call.record",
            "payload": {
                "tool_name": "exportFile",
                "invocation_id": "inv_chart1",
                "arguments": {"path": "/mnt/data/chart1.png"},
            },
            "when": 3,
        },
        # Tool 1 result: PDF created
        {
            "execution_point": "step.tool_result.record",
            "payload": {
                "ok": True,
                "invocation_id": "inv_pdf",
                "files_created": ["/mnt/data/report.pdf"],
                "delta_summary": "Exported PDF report",
            },
            "when": 4,
        },
        # Tool 2 result: Chart created
        {
            "execution_point": "step.tool_result.record",
            "payload": {
                "ok": True,
                "invocation_id": "inv_chart1",
                "files_created": ["/mnt/data/chart1.png"],
                "delta_summary": "Exported Chart 1",
            },
            "when": 5,
        },
    ]

    doc = fold_step_tree(events, run_id="r_concurrent")
    assert len(doc.steps) == 1
    step = doc.steps[0]

    # Verify both tool calls and results are preserved without being overwritten
    assert len(step.tool_calls) == 2
    assert {tc.invocation_id for tc in step.tool_calls} == {"inv_pdf", "inv_chart1"}

    assert len(step.tool_results) == 2
    assert {tr.invocation_id for tr in step.tool_results} == {"inv_pdf", "inv_chart1"}

    # Verify both files (especially the PDF) are in doc.cumulative_files()
    cum_files = doc.cumulative_files()
    assert "/mnt/data/report.pdf" in cum_files
    assert "/mnt/data/chart1.png" in cum_files
