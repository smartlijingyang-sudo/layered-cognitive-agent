from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType
from lca.contracts.models.vocal.wake import WakeContext, WakeSource
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.middleware import ReplyFirstMiddleware


def test_middleware_injects_reminder_before_ack():
    wake = WakeContext(source=WakeSource.USER_INPUT, requires_reply_first=True)
    gate = GatedVocalGate("op_1", wake_context=wake)
    middleware = ReplyFirstMiddleware()

    prompt = middleware.augment_prompt("Original Prompt", gate)
    assert "[Reply-First 契约]" in prompt
    assert "send_message" in prompt


def test_middleware_stops_injecting_after_ack():
    wake = WakeContext(source=WakeSource.USER_INPUT, requires_reply_first=True)
    gate = GatedVocalGate("op_2", wake_context=wake)
    middleware = ReplyFirstMiddleware()

    gate.deliver(SendMessagePayload(type=VocalMessageType.TEXT, content="正在为你排查..."))
    assert gate.has_acked is True

    prompt = middleware.augment_prompt("Original Prompt", gate)
    assert "[Reply-First 契约]" not in prompt
    assert prompt == "Original Prompt"


def test_middleware_no_injection_for_routine():
    wake = WakeContext(source=WakeSource.ROUTINE, requires_reply_first=False)
    gate = GatedVocalGate("op_3", wake_context=wake)
    middleware = ReplyFirstMiddleware()

    prompt = middleware.augment_prompt("Routine Prompt", gate)
    assert "[Reply-First 契约]" not in prompt
