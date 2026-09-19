| Task ID | Description | Status | Evidence |
|---|---|---|---|
| PR1-T1 | `JournalStep` 数据模型升级为复数一等公民（增加 `tool_calls`, `tool_results`, `invocation_id`） | Completed | commit 783be6198, tests/contracts/models/observability/test_journal_step_plural.py 2 passed |
| PR1-T2 | `journal_fold.py` 收集逻辑升级为并发工具字典映射（消除多工具覆盖抹除） | Completed | commit e9a92f443, 45 passed in tests/plugins/session/derivers/step_tree/ |
| PR1-T3 | Doctor H7 精准集合对账（废除脆弱的步骤数启发式） | Completed | commit e5d88cf49, tests/plugins/transport/webserver/doctor/test_doctor_h7_reconciliation.py 3 passed |
| PR2-T4 | 前端 Wire 层恢复 Token 预算感知有效上下文序列（`executeGatewayRun.ts`） | Completed | commit 4408df0b5, executeGatewayRun.ts 恢复 multi-turn 会话序列与附件绑定 |
| PR2-T5 | 后端 `RunSessionWriterProtocol.seed_prior_turns` 协议与实现 | Completed | commit db0b21065, tests/runtime/session/test_seed_prior_turns.py 4 passed |
| PR2-T6 | 接入 `runtime_loop.py` 并彻底废除 `PRIOR_CONVERSATION_WM_KEY` 伪通道 | Completed | tests/runtime/loop/test_runtime_loop_prior_turns.py 3 passed, C4 & C3 验证通过 |
| PR3-T7 | 修复 `bundles/outer/phase_main.yaml` 拓扑路由（打通 `reflect` 与 `remember` 闭环） | Completed | tests/harness/graph/test_phase_main_outer_topology.py 4 passed, test_predicate_edge_evaluation.py 5 passed |
| PR3-T8 | 门禁快速路径防护（Fast-Path Zero-Cost Gate, 保证常态无异常回复零额外开销） | Completed | tests/nodes/test_zero_cost_fast_path.py 4 passed (<2ms fast-path, _is_failure(None)=False) |
| PR4-T9 | 沙箱系统级 Fontconfig CJK 字体别名映射与事务工作区隔离 | Pending | 待开始实施 |
| PR5-T10 | 声明式记忆图节点化与自适应程序性经验（SOP）沉淀机制 | Pending | 待开始实施 |
