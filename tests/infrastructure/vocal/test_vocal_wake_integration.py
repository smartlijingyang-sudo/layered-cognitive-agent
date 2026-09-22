import pytest

from lca.contracts.models.vocal.wake import WakeContext, WakeSource
from lca.infrastructure.vocal.exceptions import UndeliveredTurnError
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard


def test_gated_gate_with_wake_context_user_input():
    wake = WakeContext(
        source=WakeSource.USER_INPUT,
        is_silence_allowed=False,
        requires_reply_first=True,
    )
    gate = GatedVocalGate("op_user", wake_context=wake)
    assert gate.wake_context.source == WakeSource.USER_INPUT
    assert gate.wake_context.requires_reply_first is True

    guard = VocalSettleGuard(gate)
    gate.handle_text_chunk("Internal scratchpad text")
    with pytest.raises(UndeliveredTurnError):
        guard.validate_turn_settle()


def test_gated_gate_with_wake_context_routine_silence():
    wake = WakeContext(
        source=WakeSource.ROUTINE,
        is_silence_allowed=True,
        requires_reply_first=False,
    )
    gate = GatedVocalGate("op_routine", wake_context=wake)
    assert gate.wake_context.is_silence_allowed is True

    guard = VocalSettleGuard(gate)
    gate.handle_text_chunk("Routine executed, no delta.")
    # is_silence_allowed=True，允许合法沉默
    assert guard.validate_turn_settle() is True


def test_gated_gate_inbound_records_channel_target():
    wake = WakeContext(
        source=WakeSource.INBOUND,
        is_silence_allowed=False,
        requires_reply_first=True,
        channel_target="wechat:user_abc",
    )
    gate = GatedVocalGate("op_inbound", wake_context=wake)
    assert gate.wake_context.channel_target == "wechat:user_abc"
