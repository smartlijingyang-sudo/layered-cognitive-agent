from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType, VocalMode
from lca.infrastructure.vocal.strategy import DirectVoiceStrategy, GatedVoiceStrategy


def test_direct_voice_strategy_emits_text_directly():
    strategy = DirectVoiceStrategy()
    assert strategy.mode == VocalMode.DIRECT
    gate = strategy.create_gate("op_1")

    # INV-VOCAL-02: 经典直通模式，普通文本直接生成对外气泡
    gate.handle_text_chunk("Hello World")
    visible = gate.get_visible_outputs()
    assert len(visible) == 1
    assert visible[0]["content"] == "Hello World"
    assert gate.get_scratchpad() == ""


def test_gated_voice_strategy_mutes_text_into_scratchpad():
    strategy = GatedVoiceStrategy()
    assert strategy.mode == VocalMode.GATED
    gate = strategy.create_gate("op_2")

    # INV-VOCAL-01: 门控模式下，大模型普通内省文本绝对不进入可见气泡
    gate.handle_text_chunk("Thinking about solution...")
    assert len(gate.get_visible_outputs()) == 0
    assert "Thinking about solution..." in gate.get_scratchpad()

    # 唯有调用 deliver 才能正式产生对外气泡
    payload = SendMessagePayload(type=VocalMessageType.TEXT, content="Official Answer")
    receipt = gate.deliver(payload)
    assert receipt.vocal_type == VocalMessageType.TEXT
    visible = gate.get_visible_outputs()
    assert len(visible) == 1
    assert visible[0]["content"] == "Official Answer"
