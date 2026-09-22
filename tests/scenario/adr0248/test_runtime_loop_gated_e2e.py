from pathlib import Path

from lca.application.initiative.hooks import evaluate_initiative
from lca.application.vocal.runtime_wiring import resolve_runtime_vocal
from lca.contracts.models.auto_review.models import AutoReviewMode
from lca.infrastructure.auto_review.gate import AutoReviewGate
from lca.infrastructure.computer.box_accessor import BoxAccessor
from lca.infrastructure.vocal.tool import SendMessageTool


def test_adr0248_full_runtime_closed_loop_e2e(tmp_path: Path):
    """验证 ADR-0248 桌面员工运行时的完整端到端生命周期：

    1. 门控声带初始化（GatedVocalGate 注入）
    2. 模型推理文本截流（进入 scratchpad，用户端 0 泄漏）
    3. Reply-first 承接气泡投递（Ack 已确认）
    4. 员工电脑沙箱文件写入与 Auto-Review 审查通过
    5. 交付正式结果气泡
    6. Settle 结算收敛成功（闭环验证）
    7. 纯函数主动提议钩子（生成 Routine 提议）
    """
    # 1. 运行态总装门控
    vocal_ctx = resolve_runtime_vocal(
        vocal_mode="gated", operation_id="run_adr248_e2e"
    )
    gate = vocal_ctx.gate
    guard = vocal_ctx.settle_guard
    assert guard is not None
    tool = SendMessageTool(gate)

    # 2. 员工机 BoxAccessor 与 AutoReview
    box = BoxAccessor(root_dir=tmp_path / "box")
    auto_review = AutoReviewGate(mode=AutoReviewMode.ENFORCE)

    # 3. 推理文本截流内省（用户不可见）
    gate.handle_text_chunk("Internal thought: checking files in /home/box...")
    assert len(gate.get_visible_outputs()) == 0
    assert "Internal thought" in gate.get_scratchpad()

    # 4. Reply-first 承接发声（用户可见）
    tool.execute(type="text", content="正在员工电脑排查环境配置...")
    assert len(gate.get_visible_outputs()) == 1
    assert gate.has_acked is True

    # 5. 员工机操作与 Auto-Review 审查
    verdict = auto_review.evaluate(
        "write_file", {"command": "write config", "path": "config.yaml"}
    )
    assert verdict.action == "allow"
    box.write_text("config.yaml", "env: production")
    assert box.read_text("config.yaml") == "env: production"

    # 6. 正式交付
    tool.execute(type="text", content="配置已更新完毕。")
    assert len(gate.get_visible_outputs()) == 2

    # 7. Settle 结算收敛
    assert guard.validate_turn_settle() is True

    # 8. 主动提议钩子
    features = {"manual_action_counts": {"write_config": 3}}
    nudge = evaluate_initiative(features)
    assert nudge is not None
    assert "例程" in nudge.nudge_message
    assert nudge.proposed_routine == "write_config"
