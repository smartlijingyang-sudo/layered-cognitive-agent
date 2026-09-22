import pytest

from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType
from lca.infrastructure.vocal.exceptions import UndeliveredTurnError
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard


def test_settle_guard_blocks_zero_delivery_for_user_input():
    gate = GatedVocalGate("op_1", wake_source="user_input")
    guard = VocalSettleGuard(gate)

    # 只有普通内省文本，没有调用 send_message 交付结果
    gate.handle_text_chunk("Done some work internally.")
    # INV-VOCAL-04: 未向用户交付结果，Settle 必拦截
    with pytest.raises(UndeliveredTurnError, match="未通过 send_message 向用户交付任何实质性结果"):
        guard.validate_turn_settle()


def test_settle_guard_passes_when_message_delivered():
    gate = GatedVocalGate("op_2", wake_source="user_input")
    guard = VocalSettleGuard(gate)

    gate.deliver(
        SendMessagePayload(
            type=VocalMessageType.TEXT, content="Final answer delivered"
        )
    )
    assert guard.validate_turn_settle() is True


def test_settle_guard_allows_silence_for_routine():
    # INV-VOCAL-06: 例程唤醒下无变化允许沉默收敛（不骚扰用户）
    gate = GatedVocalGate("op_3", wake_source="routine")
    guard = VocalSettleGuard(gate)

    gate.handle_text_chunk("No changes detected in routine check.")
    assert guard.validate_turn_settle() is True
