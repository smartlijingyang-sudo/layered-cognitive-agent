"""One-shot probe: does ``DefaultModelContextAssembler.assemble`` reflect prior
``body.tool.execute.end`` surface events in step N+1?

Goal: prove whether the 8-step think loop is caused by
``assemble_model_history`` not folding prior tool_result into the next
``messages`` payload, BEFORE touching any production code.

This is a read-only probe.  It does not modify LCA state, registries,
or fixtures; it only constructs a private Session, appends synthetic
surface events, and prints the messages list the assembler returns at
``step=1`` and ``step=2``.
"""

from __future__ import annotations

import json

from lca.infrastructure.session.context.model_context_assembler import (
    DefaultModelContextAssembler,
)
from lca.session.append import Session
from lca_kernel.events.fold.fold import (
    REQUEST_HEADER_CATEGORY,
    SURFACE_ASSISTANT_TYPE,
    SURFACE_TOOL_RESULT_TYPE,
    SURFACE_USER_TYPE,
)


def _seed_ping(session: Session) -> None:
    session.append("turn.started.v1", {"turn": 1})
    session.append("step.started.v1", {"turn": 1, "step": 1})
    session.append("message.accepted.v1", {"message_id": "m1", "role": "user", "content_ref": "ping"})
    session.append(
        SURFACE_USER_TYPE,
        {"content": "ping", "messages": [{"role": "user", "content": "ping"}]},
        surface_op="append",
    )
    session.append(
        REQUEST_HEADER_CATEGORY,
        {
            "config": {"model": "test"},
            "system": "sys",
            "messages": [{"role": "user", "content": "ping"}],
        },
    )


def _seed_tool_result(session: Session) -> None:
    """After step 1: assistant requested listFiles, body returned []."""
    session.append(
        SURFACE_ASSISTANT_TYPE,
        {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "toolu_22e7",
                        "type": "function",
                        "function": {
                            "name": "listFiles",
                            "arguments": json.dumps({"directoryPath": "/etc/hostname"}),
                        },
                    }
                ],
            }
        },
        surface_op="append",
    )
    session.append("assistant.responded.v1", {"turn": 1, "step": 1, "tool_calls": 1})
    session.append(
        SURFACE_TOOL_RESULT_TYPE,
        {
            "tool_name": "listFiles",
            "invocation_id": "toolu_22e7",
            "attempt": 1,
            "outcome": "success",
            "ok": True,
            "message": {
                "role": "tool",
                "tool_call_id": "toolu_22e7",
                "content": "[]",
            },
        },
        surface_op="append",
    )
    session.append("step.ended.v1", {"turn": 1, "step": 1})


def test_assemble_messages_grow_after_tool_result() -> None:
    session = Session("probe_assemble_growth")
    _seed_ping(session)
    assembler = DefaultModelContextAssembler()

    out_step1 = assembler.assemble(session, step=1)
    msgs1 = list(out_step1.messages)
    print("\n[PROBE] step=1 messages:")
    for i, m in enumerate(msgs1):
        print(f"  [{i}] role={m.get('role')!r} keys={sorted(m.keys())}")

    _seed_tool_result(session)
    out_step2 = assembler.assemble(session, step=2)
    msgs2 = list(out_step2.messages)
    print("\n[PROBE] step=2 messages (after tool_result surface appended):")
    for i, m in enumerate(msgs2):
        print(f"  [{i}] role={m.get('role')!r} keys={sorted(m.keys())}")

    # === The diagnosis we care about ===
    # If step=2 still only has the user "ping" message, the fold path is the
    # bug location.  If step=2 grew to include the assistant tool_call and
    # the tool result, the bug is upstream (e.g. session never bound at
    # call time → ``assemble_model_history`` short-circuits to ``[]``).
    roles2 = [m.get("role") for m in msgs2]
    assert "tool" in roles2, (
        f"DIAG: step=2 messages do not contain 'tool' role.  "
        f"Got roles={roles2}.  The fold path is NOT reflecting "
        f"prior tool_result into the next LLM request."
    )
