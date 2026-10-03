# ADR-0282：被拒 tool call 入 journal 契约（派发前拒绝必须留事实）

## 状态

**Proposed — 2026-10-04**

> **一句话**：`UseToolOperation.execute()` 的三条派发前闸门（wire 状态 / 未暴露工具 / 参数缺失）拒绝一个 call 时，必须先经 `_journal_blocked_call()` 在 step 树里留下 `step.tool_call.record(status="wire_blocked")` + `step.tool_result.record(outcome="failure", ok=False)` 这一对事实再返回——`8c51d49de` 已在实现层落地，本 ADR 把它写成契约，钉住"拒绝也要写实"的语义与待拍板项。

## 0. 接任务前 7 问（精简自检）

1. 谁受益？读 journal 做诊断的人和机器：`ToolDeriver`（doctor/deep-health）、`debug-run` 的 `error_ref`、事后审计——它们只读 journal 事实。
2. 真实问题？实现已落地（`8c51d49de fix(body): journal tool calls the wire gate refuses`，2026-10-04 02:03），但 **docs/** 对 `wire_blocked` 零提及（本轮 grep 实证）——契约只存在于代码和测试里；且问题本身是实锤的：`run_56c3352cd22e` 的 10 个 tool call 被拒 2 个（`execute_code`、`google_drive_export_file`，`failure_kind=tool_wire`，deferred namespace 未加载），manifest 仍读 `"ok (3 steps, 8 tools)"`、`conditions_degraded=0`——doctor 撒谎了。
3. 删掉会坏什么？不坏——本 ADR 是收敛记录，不新增行为；但"拒绝也要写实"的语义会继续只存在于实现者脑中，任一重构闸门逻辑的人可能静默丢掉 `_journal_blocked_call`。
4. 更简单方案？只在 backlog 记一笔。否决：这是 ADR-0260 写盘铁律的"派发前拒绝"分支（0260 C3 的五条写的是"落笔前写盘/冲突原地修正/当场写/先读后写"——拒绝路径是缺口），且与 ADR-0276 证据分级（"证据不到 L2 就不下诊断结论"）直接相关：医生（ToolDeriver）之前是"无证据→判 ok"，现在"有证据→判 degraded"。
5. 契约先行？否——语义已在实现+测试中落地（见 §1），本 ADR 只做"名实相符"的收敛记录，状态诚实标 Proposed。
6. 与现有 ADR 冲突？无。0260 C1（写盘确认门）管"落盘才算发生"；本 ADR 是 C1 在"被拒绝的调用"上的特例：**拒绝本身也是发生的事实，必须落盘**。0047（wire 状态禁止执行）管"不许执行"；本 ADR 管"不许执行时 journal 不许缺席"。
7. 状态诚实？Proposed。`latency_ms=0` 的口径、deriver 的判定规则归属、拒绝事实的留存期限，全部待拍板，见 §3。

## 1. 实证（main@8c51d49de）

### 1.1 落点

`lca/cognition/body/actions/action_handlers.py`：

- `_journal_blocked_call(decision, block)`（:171-217）：从 `decision.tool_calls` 按 `block.tool_call_id` 找回原始 call；`invocation_id` 用 block 的 tool_call_id（空则合成 `inv{新 id}`）；写 `record_step_tool_call(status="wire_blocked", arguments_summary=summarize_args(...))` + `record_step_tool_result(outcome="failure", ok=False, failure_kind=block.extra[FAILURE_KIND])`。
- `UseToolOperation.execute` 的三条闸门各经它返回（:245-253）：
  1. `tool_wire_block_observation(decision)`——ADR-0047：`tool_wire_status` 为 incomplete/invalid，禁止执行；
  2. `unexposed_tool_block_observation(decision)`——工具在未加载的 deferred namespace 里（`failure_kind=tool_wire`）；
  3. `missing_arguments_block_observation(decision, registry)`——ADR-0047：必需参数从未到达，不许带空 payload 执行。

### 1.2 为什么非 SafeExecutor 不可被替代

`SafeExecutor` 是 `step.tool_call.record` / `step.tool_result.record` 的唯一发射器；被拒的 call 永远到不了它。模型侧不受影响（`effect.execute` 在自己的路径上写 surface/tool_result 行，所以模型收到了拒绝）——**盲的只是 run 诊断**：`ToolDeriver` 只读那两个 execution point，无事实可读就报 `tool=ok`。拒绝入 journal 后，匹配的 call/result 对让 orphan 检查保持安静，`tool` 健康翻为 degraded、`reason=tool_result_failed`、证据指向拒绝本身。

### 1.3 契约测试（已存在）

- `tests/cognition/body/test_blocked_tool_call_is_journaled.py`（261 行）：用真实的 `UseToolOperation` + 真实的 `record_step_tool_*` commits + 真实 `Session` + 真实 `ToolDeriver`，三条闸门各一轮——修改前三轮全红（"the refused call left no step.tool_call.record"），修改后全绿。
- commit 自述的回归面：`tests/observability`、`tests/cognition/body`、`tests/persistence`、`tests/infrastructure/cli`、`tests/session`、`tests/lca_plugins`、`tests/transport`、`tests/integration`、`tests/plugins/{observability,session}`、`tests/journal`、`tests/lca_kernel`——失败集修改前后同为 11 个 pre-existing（按名一致），ruff 全净。

### 1.4 反向缺口

`docs/` 全仓 grep `wire_blocked` **零命中**（本轮实证）；`docs/observability/journal-v2-schema.md` 未登记 `wire_blocked` 这个 status 取值。写闸门的人如果不知道"拒绝要写实"的存在，重构时删掉 `_journal_blocked_call` 调用，测试会红（契约钉在），但文档不会提醒。

## 2. 契约

- **C1（拒绝写实，现状已落地）**：`UseToolOperation.execute` 的任何派发前拒绝路径（当前三条：wire 状态 / 未暴露工具 / 参数缺失），必须在返回 block Observation 之前先留下 call+result 这一对 journal 事实。拒绝是发生的事件，不是"没发生"——journal 记录"发生了什么"，不只记录"执行了什么"。
- **C2（状态区分，现状已落地）**：被拒的 call 用 `status="wire_blocked"`，与"跑了但失败"的普通 failure 区分；`latency_ms` 恒为 0（没执行过，耗时就是 0——不许填墙钟差）。
- **C3（失败原因透传，现状已落地）**：result 事实的 `failure_kind` 取自 `block.extra[FAILURE_KIND]`（如 `tool_wire`），`error`/`delta_summary` 带拒绝原文（截 120 字）——deriver 的 degraded 结论必须能指向拒绝原因，而不是一个裸 failure。
- **C4（新增闸门纪律）**：任何新增的派发前拒绝路径必须① 经 `_journal_blocked_call()`（或等价）留事实、② 补一条"拒绝前有 step.tool_call.record"的契约测试（§1.3 同款手法），缺一即违反本契约。
- **C5（边界声明，未裁决）**：本契约当前只覆盖 `UseToolOperation` 的派发前拒绝；HIL 审批拒绝（`status="pending_approval"` 那条，ToolDeriver 已 special-case）、用户取消、预算熔断等其他"没执行"的路径，是否同等写实，见待拍板②。

## 3. 待拍板（需李超/Athena 裁决，arch 轮不擅自决定）

1. **`latency_ms=0` 的口径**：当前实现写 0（"没执行过"）。备选：写闸门判定耗时（µs 级）或留 null。0 的好处是"拒绝≠执行"的二分干净；坏处是与"耗时恒有值"的统计口径冲突。需裁决。
2. **其他"没执行"路径**：HIL 审批拒绝、用户取消、预算熔断——是否全部按 C1 写实？本 ADR 只钉了三条派发前闸门；`pending_approval` 已被 ToolDeriver special-case，说明"拒绝"家族已有先例但未统一。需裁决：统一成"任何拒绝都写实"，还是保持现状逐个立案。
3. **拒绝事实的留存/聚合**：`run_56c3352cd22e` 的 manifest 之前读 `"ok (3 steps, 8 tools)"`——被拒的 2 个 call 现在进了 journal，manifest 的 tool 计数语义是否要变（"10 次尝试，8 成功 2 被拒" vs "8 tools"）？需裁决。
4. **与 0276 的归属**：本契约的证据分级（拒绝事实算 L2 证据）是否并入 ADR-0276 的证据映射表，还是独立成篇？arch 只提案。

## 4. 验收（给 tests/quality lane）

- **T1**（已有，`test_blocked_tool_call_is_journaled.py`）：三条闸门各一轮——真实 `UseToolOperation` 拒绝后 `step.tool_call.record(status="wire_blocked")` 与 `step.tool_result.record(ok=False)` 成对存在；只引用，不重复钉。
- **T2**（tests lane 可认领）：新增闸门扫描——`execute()` 内所有 `return *_block_observation(...)` 的返回点，必须经 `_journal_blocked_call`（AST 级扫描测试，防重构静默丢弃）。

## 决策记录

（空。待李超/Athena 裁决后填写。）
