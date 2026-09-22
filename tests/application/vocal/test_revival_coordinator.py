from lca.application.vocal.revival import RevivalCoordinator
from lca.contracts.models.vocal.wake import WakeSource
from lca.infrastructure.vocal.strategy import GatedVoiceStrategy


def test_revival_coordinator_handles_subagent_completion():
    strategy = GatedVoiceStrategy()
    # 1. 父进程拥有声带
    parent_gate = strategy.create_gate("parent_op")
    revival_coord = RevivalCoordinator(parent_gate)

    # 2. 模拟子代理完成并上报
    subagent_result = {
        "subagent_id": "sub_parser_42",
        "status": "completed",
        "summary": "已成功分析 100 个文件，发现 2 处潜在内存泄漏。",
    }

    wake_ctx, delivery_receipt = revival_coord.handle_subagent_completion(
        subagent_result
    )

    # 3. 验证唤醒源为 REVIVAL
    assert wake_ctx.source == WakeSource.REVIVAL
    assert wake_ctx.subagent_id == "sub_parser_42"

    # 4. 验证由父进程统一发声交付
    assert delivery_receipt.vocal_type == "text"
    visible = parent_gate.get_visible_outputs()
    assert len(visible) == 1
    assert "已成功分析 100 个文件" in visible[0]["content"]
