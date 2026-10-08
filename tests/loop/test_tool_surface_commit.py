"""commit_body_tool_execute_end surface append (ADR-0201)."""

from __future__ import annotations

from lca.cognition.body.emit.observation_surface import observation_content
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.external_content import (
    ContentOrigin,
    fence_external_content,
)
from lca.infrastructure.session.context.model_context_assembler import DefaultModelContextAssembler
from lca.loop.commit.tool_journal import commit_body_tool_execute_end
from lca.plugins.session.projection_registry.projection_registry import ProjectionRegistry
from lca.plugins.session.session_model_visible.session_model_visible import ModelVisibleUnit
from lca.session.append import Session


def test_commit_body_tool_execute_end_appends_tool_role_message() -> None:
    registry = ProjectionRegistry()
    registry.register(ModelVisibleUnit())
    session = Session("commit_surface_1")
    registry.register_to(session)
    receipt = commit_body_tool_execute_end(
        tool_name="executeCode",
        invocation_id="toolu_abc",
        attempt=1,
        outcome="success",
        latency_ms=12,
        observation=Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"stdout": "page one"},
        ),
        session=session,
    )
    assert receipt is not None
    assembled = DefaultModelContextAssembler().assemble(session, step=1)
    tool_msgs = [m for m in assembled.messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "toolu_abc"
    # Production convention (observation_content): dict payloads JSON-encode.
    # ADR-0292 C1: external observations are fenced in the tool message
    # (one source, two renderings — the envelope's content_origin mark).
    assert tool_msgs[0]["content"] == fence_external_content('{"stdout": "page one"}')
def test_journal_persists_display_projection_not_absolute_paths() -> None:
    """RA-034(a) as revised by 8094cc234: journal content == ``observation_content()`` verbatim.

    The display-path projection moved into guest emit
    (``computer/guest/preamble.py``): by the time an observation reaches
    ``observation_content()`` its structured path fields are already in
    workspace-relative display form. ``commit_body_tool_execute_end``
    persists that text verbatim — no second projection, no absolute-path
    copy anywhere on the write path.
    """
    session = Session("journal_display_pin")
    # Post-emit display form: emit() already projected the guest path to
    # workspace-relative; observation_content() must persist it unchanged.
    obs = Observation(
        observation_id=new_id("obs"),
        success=True,
        payload={"path": "a.xlsx"},
        content_origin=ContentOrigin.INTERNAL,
    )
    receipt = commit_body_tool_execute_end(
        tool_name="executeCode",
        invocation_id="toolu_pin",
        observation=obs,
        session=session,
    )
    assert receipt is not None
    from lca_kernel.events.fold.inputs import SURFACE_TOOL_RESULT_TYPE

    events = [e for e in session.snapshot_events() if e.type == SURFACE_TOOL_RESULT_TYPE]
    assert len(events) == 1
    content = events[0].payload["content"]
    assert content == observation_content(obs)
    assert content == '{"path": "a.xlsx"}'
