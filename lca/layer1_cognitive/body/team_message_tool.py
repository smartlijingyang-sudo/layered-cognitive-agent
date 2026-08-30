"""Team Message publish tool (PR9 / D25).

The tool is the single entry point for an agent to publish a message
on its team's topic.  All team messages on a team share one topic
(``team_id``); delegation sub-threads use ``thread_id``.

The emitted ``TeamMessagePublished`` event is the canonical journal
record.  The ``sensor.team-inbox`` sensor (PR9) folds it into the
next think's ``ContextManifest``.
"""

from __future__ import annotations

from lca.contracts.atoms.ids import new_id
from lca.contracts.models.observability.journal import TeamMessagePublished
from lca.infrastructure.observability import record as _journal_record


def publish_team_message(
    *,
    team_id: str,
    thread_id: str,
    sender_role: str,
    recipient_role: str,
    body: str,
    step: int = 0,
) -> TeamMessagePublished:
    """Publish a team message and emit the canonical journal event.

    The function is the body-side entry point; callers wrap it through
    the ActionRegistry so the tool is invokable via the regular
    ``use_tool`` pipeline.
    """
    event = TeamMessagePublished(
        team_id=team_id,
        thread_id=thread_id,
        sender_role=sender_role,
        recipient_role=recipient_role,
        step=step,
        body_preview=body,
    )
    _journal_record(event)
    return event


TEAM_MESSAGE_TOOL_NAME = "team.message-publish"


def build_team_message_publish_tool() -> object:
    """Return the ``Tool`` instance for the ActionRegistry.

    The tool is a thin wrapper around ``publish_team_message``.  The
    registry wires up the standard tool schema.
    """
    from lca.contracts.models.core.decision import Observation
    from lca.contracts.protocols.infra import Tool

    class _TeamMessagePublishTool(Tool):
        def __init__(self) -> None:
            self.name = TEAM_MESSAGE_TOOL_NAME
            self.description = "Publish a message on the team's topic."
            self.parameters = {
                "type": "object",
                "properties": {
                    "team_id": {"type": "string"},
                    "thread_id": {"type": "string"},
                    "recipient_role": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["team_id", "thread_id", "recipient_role", "body"],
            }
            self.is_idempotent = True
            self.default_timeout_s = 5

        async def execute(self, args: dict) -> Observation:
            event = publish_team_message(
                team_id=str(args["team_id"]),
                thread_id=str(args["thread_id"]),
                sender_role="agent",
                recipient_role=str(args["recipient_role"]),
                body=str(args["body"]),
            )
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={"event_id": new_id("event"), "team_id": event.team_id},
            )

        def validate(self, args: dict) -> str | None:
            for key in ("team_id", "thread_id", "recipient_role", "body"):
                if key not in args or not args[key]:
                    return f"missing required field: {key}"
            return None

    return _TeamMessagePublishTool()
