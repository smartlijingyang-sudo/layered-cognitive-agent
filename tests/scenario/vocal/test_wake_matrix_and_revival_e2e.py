from lca.application.vocal.factory import VocalStrategyFactory
from lca.application.vocal.revival import RevivalCoordinator
from lca.contracts.models.vocal.models import SendMessagePayload, VocalMessageType
from lca.contracts.models.vocal.wake import WakeSource
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard
from lca.infrastructure.vocal.tool_filter import VocalToolFilter
from lca.infrastructure.vocal.wake import WakeClassifier


def test_e2e_routine_silent_execution_flow():
    classifier = WakeClassifier()
    wake = classifier.classify(WakeSource.ROUTINE)

    factory = VocalStrategyFactory()
    strategy = factory.resolve_strategy("gated")
    gate = strategy.create_gate("run_routine_1", wake_source=wake.source, wake_context=wake)
    guard = VocalSettleGuard(gate)

    gate.handle_text_chunk("Routine health-check: all systems normal, no action required.")
    assert len(gate.get_visible_outputs()) == 0
    assert guard.validate_turn_settle() is True


def test_e2e_inbound_channel_directed_flow():
    classifier = WakeClassifier()
    wake = classifier.classify(WakeSource.INBOUND, channel_target="wechat:gh_123456")

    factory = VocalStrategyFactory()
    strategy = factory.resolve_strategy("gated")
    gate = strategy.create_gate("run_inbound_1", wake_context=wake)

    # 模型进行回复
    gate.deliver(
        SendMessagePayload(
            type=VocalMessageType.TEXT,
            content="收到微信入站消息，已自动处理。",
        )
    )

    visible = gate.get_visible_outputs()
    assert len(visible) == 1
    assert visible[0]["content"] == "收到微信入站消息，已自动处理。"
    assert visible[0]["channel_target"] == "wechat:gh_123456"


def test_e2e_subagent_mute_and_revival_flow():
    # 1. 协调者拥有完整工具集（含 send_message）
    tool_filter = VocalToolFilter()
    coord_tools = tool_filter.filter_tools_for_runtime(
        ["run_command", "send_message"], origin="user"
    )
    assert "send_message" in coord_tools

    # 2. 子代理被物理禁声（剥离 send_message）
    sub_tools = tool_filter.filter_tools_for_runtime(coord_tools, origin="subagent")
    assert "send_message" not in sub_tools

    # 3. 父进程建立门控
    factory = VocalStrategyFactory()
    parent_gate = factory.resolve_strategy("gated").create_gate("parent_run")

    # 4. 子代理静默执行产出
    subagent_outcome = {
        "subagent_id": "sub_audit_99",
        "status": "completed",
        "summary": "发现并修复 3 处配置漂移。",
    }

    # 5. 后台复苏唤醒父协调者交付
    revival_coord = RevivalCoordinator(parent_gate)
    wake, receipt = revival_coord.handle_subagent_completion(subagent_outcome)
    assert wake.source == WakeSource.REVIVAL
    assert receipt.vocal_type == "text"
    assert len(parent_gate.get_visible_outputs()) == 1
    assert "发现并修复 3 处配置漂移" in parent_gate.get_visible_outputs()[0]["content"]
