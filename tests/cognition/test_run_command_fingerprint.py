"""runCommand intent normalization for loop detection."""

from __future__ import annotations

from lca.cognition.brain.decision_gates.loop.fingerprint import tool_call_fingerprint
from lca.contracts.models.core.execution.decision import ToolCall


def test_officecli_read_variants_share_fingerprint() -> None:
    a = ToolCall(
        call_id="a",
        tool_name="runCommand",
        arguments={
            "command": 'cd /mnt/data && officecli read "4.算力资源使用报告模板.docx"',
        },
    )
    b = ToolCall(
        call_id="b",
        tool_name="runCommand",
        arguments={
            "command": 'officecli read "/mnt/data/4.算力资源使用报告模板.docx"',
        },
    )
    assert tool_call_fingerprint(a) == tool_call_fingerprint(b)
