"""Grok Bot production alignment closed-loop integration scenario (ADR-0248 / s01~s16).

Verifies invariants INV-01 through INV-09:
- INV-01: Gated 模式流式内省文本 100% 截流进 scratchpad，绝不进可见气泡
- INV-02: 仅经由 send_message 交付正式气泡，并追加 vocal.message.delivered 事实
- INV-03: Widget 选项卡触发停等挂起（WAITING_INPUT），同轮二次发声报错阻断，提交 answer 顺畅恢复
- INV-04: 员工机容器/受限沙箱隔离，越界抛 PermissionError，禁止提权命令 (sudo/su)
- INV-05: 浏览器子代理工具集物理剔除 send_message，绝对零对用户通道发声能力
- INV-06: 单屏桌面互斥锁（allocateWindow / freeWindow）严格互斥，具备 TTL 超时防死锁
- INV-07: 例程唤醒具备合法沉默放行（is_silence_allowed=True），0 消息交付正常收敛
- INV-08: Token 超预算立即熔断阻断触发（SpendGuard）
- INV-09: 经典 direct 模式 100% 零退化，直连普通文本即为最终输出
"""

from __future__ import annotations

import asyncio

import pytest

from lca.application.routine.scheduler import RoutineSchedulerService
from lca.application.routine.spend_guard import SpendGuard
from lca.contracts.models.core.execution.decision import ToolCall, requires_human_input
from lca.contracts.models.routine.models import RoutineSpec
from lca.contracts.models.vocal.wake import WakeSource
from lca.domain.routine.repository import JsonRoutineRepository
from lca.infrastructure.browser.subagent import BrowserSubagent
from lca.infrastructure.computer.box_sandbox_adapter import LocalBoxAdapter
from lca.infrastructure.computer.desktop_lock import DesktopLockManager
from lca.infrastructure.runtime_plane.capability_bindings import (
    BindingsViewBuilder,
    reset_capability_bindings,
    set_capability_bindings,
)
from lca.infrastructure.vocal.exceptions import VocalGateAlreadyBlockedError
from lca.infrastructure.vocal.gate import DirectVocalGate, GatedVocalGate
from lca.infrastructure.vocal.settle_guard import VocalSettleGuard
from lca.infrastructure.vocal.tool import SendMessageTool
from lca.infrastructure.vocal.tool_adapter import SendMessageVocalTool
from lca.plugins.events.publishers._session_publish import (
    reset_publish_session,
    set_publish_session,
)
from lca.session.append import Session


@pytest.mark.asyncio
async def test_inv_01_and_02_vocal_streaming_interception_and_bubble_delivery():
    """INV-01 & INV-02: 流式内省文本截流与 send_message 真实交付事实。"""
    session = Session("sess_closed_loop_1")
    set_publish_session(session)
    gate = GatedVocalGate(operation_id="op_gated_1")

    # 1. 模拟流式生成中间思考过程 -> 全部进入 scratchpad，可见输出为 0
    gate.handle_text_chunk("Thought: I need to check the repository status.\n")
    gate.handle_text_chunk("Thought: Now let me inspect the commit history.\n")
    assert len(gate.get_visible_outputs()) == 0
    assert "Thought: I need to check" in gate.get_scratchpad()
    assert "Now let me inspect" in gate.get_scratchpad()

    # 2. 模拟工具调用 send_message 交付正式气泡
    token = set_capability_bindings(BindingsViewBuilder(vocal_mode="gated", vocal_gate=gate))
    try:
        tool = SendMessageVocalTool(gate)
        obs = await tool.execute({"type": "text", "content": "仓库检查完毕，所有提交符合规范。"})
        assert obs.success is True
        assert obs.payload["content"] == "仓库检查完毕，所有提交符合规范。"

        # 可见气泡恰好有 1 条正式消息
        visible = gate.get_visible_outputs()
        assert len(visible) == 1
        assert visible[0]["content"] == "仓库检查完毕，所有提交符合规范。"

        # Session 记录不可变交付事实事件
        facts = [e for e in session._log if e.type == "vocal.message.delivered"]
        assert len(facts) == 1
        assert facts[0].data["content"] == "仓库检查完毕，所有提交符合规范。"
        assert facts[0].visibility == "user"

        # 3. 轮次结算核验放行
        settle_guard = VocalSettleGuard(gate)
        assert settle_guard.validate_turn_settle() is True
    finally:
        reset_capability_bindings(token)
        reset_publish_session(None)


def test_inv_03_widget_stop_and_wait_and_vocal_blocking():
    """INV-03: Widget 触发 WAITING_INPUT 停等，同轮二次发声报错阻断，恢复后正常。"""
    gate = GatedVocalGate(operation_id="op_widget_loop")
    tool = SendMessageTool(gate)

    # 1. 交付交互选项卡
    res = tool.execute(
        type="widget",
        content="请选择目标服务器：",
        options=[{"id": "node_a", "label": "节点 A"}, {"id": "node_b", "label": "节点 B"}],
    )
    assert res["is_terminal_for_turn"] is True
    assert gate.is_awaiting_widget() is True

    # 2. 同轮严禁二次发声（硬阻断）
    with pytest.raises(VocalGateAlreadyBlockedError):
        tool.execute(type="text", content="这是不被允许的附言")

    # 3. 契约层识别需要用户交互
    call = ToolCall(call_id="c_w", tool_name="send_message", arguments={"type": "widget"})
    assert requires_human_input([call]) is True

    # 4. 人工选择恢复后重置标志，次轮正常发声
    gate.reset_awaiting_widget()
    assert gate.is_awaiting_widget() is False
    next_res = tool.execute(type="text", content="已连接到节点 A。")
    assert next_res["status"] == "delivered"


@pytest.mark.asyncio
async def test_inv_04_box_sandbox_isolation_and_containment(tmp_path):
    """INV-04: 员工机沙箱隔离，跨越沙箱根目录报 PermissionError，禁止提权命令。"""
    box_root = tmp_path / "employee_box"
    adapter = LocalBoxAdapter(root_dir=box_root)

    # 正常读写
    await adapter.write_file("data/result.json", '{"status": "ok"}')
    content = await adapter.read_file("data/result.json")
    assert '{"status": "ok"}' in content

    # 越界拦截
    with pytest.raises(PermissionError, match="超出员工电脑沙箱范围"):
        await adapter.read_file("../../../etc/shadow")

    # 提权拦截
    with pytest.raises(PermissionError, match="禁止提权命令"):
        await adapter.run_command("sudo apt-get update")


def test_inv_05_browser_subagent_vocal_isolation():
    """INV-05: 浏览器子代理工具集物理剔除 send_message，绝对零发声能力。"""
    subagent = BrowserSubagent(agent_id="browser_sub_1")
    tool_names = [t.name for t in subagent.get_tools()]
    assert "send_message" not in tool_names
    assert "browser_navigate" in tool_names
    assert "browser_screenshot" in tool_names


@pytest.mark.asyncio
async def test_inv_06_desktop_lock_mutual_exclusion_and_ttl():
    """INV-06: 桌面单屏互斥锁严格互斥与 TTL 防死锁。"""
    lock_mgr = DesktopLockManager(default_ttl_s=1)

    # 抢占锁
    assert await lock_mgr.allocate_window("agent_alpha", "sess_1") is True
    # 冲突被拒
    assert await lock_mgr.allocate_window("agent_beta", "sess_1") is False

    # 等待 TTL 超时自动回收
    await asyncio.sleep(1.1)
    # 超时后其他 agent 抢占成功
    assert await lock_mgr.allocate_window("agent_beta", "sess_1") is True
    assert lock_mgr.get_current_owner() == "agent_beta"

    # 主动归还
    assert await lock_mgr.free_window("agent_beta", "sess_1") is True
    assert lock_mgr.is_locked() is False


def test_inv_07_and_08_routine_legal_silence_and_spend_fusing(tmp_path):
    """INV-07 & INV-08: 例程合法沉默放行与超预算立即熔断。"""
    repo = JsonRoutineRepository(storage_dir=tmp_path / "routines")
    guard = SpendGuard()
    scheduler = RoutineSchedulerService(repository=repo, spend_guard=guard)

    spec = RoutineSpec(
        id="rt_monitor",
        name="监控例程",
        interval_seconds=300,
        prompt="定期巡检",
        assistant_id="asst_monitor",
        daily_budget_tokens=2000,
    )
    repo.save(spec)

    # 1. 验证常规例程执行拥有合法沉默属性
    gate = GatedVocalGate(operation_id="op_routine_1", wake_source=WakeSource.ROUTINE)
    assert gate.wake_context.is_silence_allowed is True
    settle = VocalSettleGuard(gate)
    # 0 消息正常收敛
    assert settle.validate_turn_settle() is True

    # 2. 消费 1500 tokens，未超预算，正常触发
    guard.record_consumption("rt_monitor", 1500)
    assert scheduler.can_trigger("rt_monitor") is True

    # 3. 消费超出 2000 tokens，立即熔断
    guard.record_consumption("rt_monitor", 600)
    assert guard.is_budget_exceeded(spec) is True
    assert scheduler.can_trigger("rt_monitor") is False


def test_inv_09_direct_vocal_mode_zero_regression():
    """INV-09: 经典 direct 模式 100% 零退化，直连普通文本即为最终输出。"""
    gate = DirectVocalGate(operation_id="op_direct")
    gate.handle_text_chunk("你好，我是经典模式。")
    outputs = gate.get_visible_outputs()
    assert len(outputs) == 1
    assert outputs[0]["content"] == "你好，我是经典模式。"

    settle = VocalSettleGuard(gate)
    assert settle.validate_turn_settle() is True
