"""commit_body_tool_execute_end surface append (ADR-0201)."""

from __future__ import annotations

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
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
    assert tool_msgs[0]["content"] == "page one"
