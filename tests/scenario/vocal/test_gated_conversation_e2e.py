from lca.application.vocal.factory import VocalStrategyFactory
from lca.contracts.models.vocal.models import VocalMode
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard
from lca.infrastructure.vocal.tool import SendMessageTool


def test_full_gated_conversation_flow_ack_then_deliver():
    factory = VocalStrategyFactory()
    strategy = factory.resolve_strategy(vocal_mode="gated")
    assert strategy.mode == VocalMode.GATED

    gate = strategy.create_gate(operation_id="run_e2e_1", wake_source="user_input")
    assert isinstance(gate, GatedVocalGate)
    tool = SendMessageTool(gate)
    guard = VocalSettleGuard(gate)

    # 1. 思考过程（被截流进内省 scratchpad，绝不进对外气泡）
    gate.handle_text_chunk("Let me read the system logs first...")
    assert len(gate.get_visible_outputs()) == 0

    # 2. Reply-first 承接气泡
    tool.execute(type="text", content="正在为你排查系统日志，请稍候...")
    assert len(gate.get_visible_outputs()) == 1
    assert gate.has_acked is True

    # 3. 模拟耗时工具排查完毕后的正式交付
    gate.handle_text_chunk(
        "Log analysis finished, found root cause in connection pool."
    )
    tool.execute(
        type="text", content="排查完成，根因为连接池耗尽，已自动扩容。"
    )
    assert len(gate.get_visible_outputs()) == 2

    # 4. Settle 结算收敛成功
    assert guard.validate_turn_settle() is True


def test_default_is_direct_strategy():
    factory = VocalStrategyFactory()
    # 默认零配置走经典直连模式，确保原有体验零回归
    strategy = factory.resolve_strategy(vocal_mode=None)
    assert strategy.mode == VocalMode.DIRECT

    gate = strategy.create_gate(operation_id="run_classic")
    gate.handle_text_chunk("Classic direct output token")
    visible = gate.get_visible_outputs()
    assert len(visible) == 1
    assert visible[0]["content"] == "Classic direct output token"


def test_gated_conversation_with_widget_flow():
    factory = VocalStrategyFactory()
    strategy = factory.resolve_strategy(vocal_mode="gated")
    gate = strategy.create_gate(operation_id="run_e2e_widget")
    tool = SendMessageTool(gate)
    guard = VocalSettleGuard(gate)

    # 下发选项卡
    res = tool.execute(
        type="widget",
        content="请选择目标发布环境",
        options=[
            {"id": "prod", "label": "生产环境", "variant": "danger"},
            {"id": "staging", "label": "预发环境", "variant": "primary"},
        ],
    )
    assert res["is_terminal_for_turn"] is True
    assert gate.is_awaiting_widget() is True
    assert len(gate.get_visible_outputs()) == 1
    assert gate.get_visible_outputs()[0]["type"] == "widget"
    assert len(gate.get_visible_outputs()[0]["options"]) == 2

    # Settle 成功放行（Widget 属于合法交付）
    assert guard.validate_turn_settle() is True
