from __future__ import annotations

from lca.contracts.harness.act.command import (
    ApprovalResumeCommand,
    CancelCommand,
    CommandKind,
    InjectCommand,
    MessageSendCommand,
    SessionCreateCommand,
    SteerCommand,
    ensure_command_id,
)


def test_each_command_exposes_stable_kind() -> None:
    commands = (
        SessionCreateCommand(idempotency_key="create-1", profile="default"),
        MessageSendCommand(
            idempotency_key="message-1",
            session_id="session-1",
            role="user",
            content="hello",
        ),
        CancelCommand(session_id="session-1"),
        ApprovalResumeCommand(
            session_id="session-1",
            approval_id="approval-1",
            payload="yes",
            idempotency_key="approval-resume-1",
        ),
        SteerCommand(session_id="session-1", content="be concise"),
        InjectCommand(session_id="session-1", source="system", content="fact"),
    )

    assert [command.kind for command in commands] == [
        CommandKind.SESSION_CREATE,
        CommandKind.MESSAGE_SEND,
        CommandKind.CANCEL,
        CommandKind.APPROVAL_RESUME,
        CommandKind.STEER,
        CommandKind.INJECT,
    ]


def test_missing_command_id_is_generated_with_kind_prefix() -> None:
    command = CancelCommand(session_id="session-1")

    command_id = ensure_command_id(command)

    assert command_id.startswith("session.cancel:")
    assert ensure_command_id(CancelCommand(session_id="session-1", command_id="fixed")) == "fixed"


def test_command_id_is_part_of_frozen_command_identity() -> None:
    command = ApprovalResumeCommand(
        session_id="session-1",
        approval_id="approval-1",
        payload="approved",
        idempotency_key="approval-resume-1",
        command_id="approval-resume-command-1",
    )

    assert command.command_id == "approval-resume-command-1"
    assert command.kind is CommandKind.APPROVAL_RESUME
