# ADR-0201 — Model-Visible Tool Result 写面闭环（补全 ADR-0193）

## 状态

**Implemented**（2026-09-07）。证据来自 `traces/runs/run_640c492b7f40`：`assemble_model_history` 路径下模型失明；根因是 **0193 写面未完成**，不是读面缺失。P1 写面 + Reflect 批语义；P2 交付 gate 与 model-visible 观测对齐。

**配套 Note**：[`docs/notes/implemented/seam/2026-09-07-tool-result-prompt-closure.md`](../notes/implemented/seam/2026-09-07-tool-result-prompt-closure.md)。

## 0. 决策摘要

Agent 在多 step think→act→think 循环中看不到上轮工具输出，每轮从原始 objective 重推。症状：`llm.request.header.messages` 中 `role=tool` 计数恒为 0。

**第一性原理：** Effect Receipt（Body 回执）≠ Model-visible 事实。Receipt 记录「执行发生了什么」；LLM FC 协议需要 `{role:tool, tool_call_id, content}` 进入 **Session surface fold**，经 `derive_messages` → `assemble_model_history` → `openai_messages_with_history` 送达模型。

**ADR-0193 已实现读面：** `SURFACE_TOOL_RESULT_TYPE = spine.body.tool.execute.end`；`ModelContextAssembler` + `assemble_model_history` 是运行时 LLM wire 唯一入口。

**本 ADR 补写面（不新增 EP）：**

```text
SafeExecutor Observation
  → commit_body_tool_execute_end
  → append_tool_result_surface (surfaceOp=append + data.message)
  → ModelVisibleUnit fold
  → assemble_model_history → LLM 看到 role=tool
```

**Sibling 修复（同 run 暴露）：**

| 缺口 | 修复 |
|---|---|
| Reflect 批部分成功误报失败 | `critic._partial_batch_reflection` → ON_TRACK |
| Delivery gate 把 PDF dump 当交付 | `task_requires_synthesis` → stdout 不算 delivery |
| spine header 缺 history merge | `ModelVisibleHookAdapter._kwargs_for_hook` 合并 wire messages |

## 1. 不变量

| ID | 不变量 |
|---|---|
| MV1 | 不新增平行 EP；复用 `body.tool.execute.end` + `SURFACE_TOOL_RESULT_TYPE` |
| MV2 | `data.message.role` MUST 为 `tool`；`tool_call_id` 与 assistant tool_calls 一致 |
| MV3 | Receipt（CursorRecord / turn.control）与 surface message 分轨；Receipt 不替代 FC message |
| MV4 | cognition 禁止直接写 model-visible message；唯一生产 `append_tool_result_surface` |
| MV5 | 合成/分析类 task 的 tool stdout 不构成 `DeliveryEvidence` 满足 |
| MV6 | `SpineLlmRequestHeaderPayload.messages` 反映 adapter 实际 wire（含 history merge） |
| MV7 | 删除 compat 前须有 `rg` / pytest delete-when 检测 |

## 2. 实现锚点

| 组件 | 路径 |
|---|---|
| 投影 | `lca/infrastructure/session/projections/tool_result_message.py` |
| Emit | `lca/infrastructure/session/emit/tool_surface_emit.py` |
| Commit | `lca/loop/commit/tool_journal.py` |
| Body 接线 | `lca/cognition/body/executor/safe_executor.py` |
| 交付谓词 | `lca/cognition/convergence/task_class.task_requires_synthesis` |
| 观测 merge | `lca/plugins/events/hooks/model_visible/adapter.py` |

## 3. delete-when

```text
body.tool.execute.end 无 surfaceOp/message:
  delete_when: commit_body_tool_execute_end 测试断言 derive_messages 含 role=tool

adapter history→messages 直拷贝 fallback:
  delete_when: test_wire_messages 通过且 rg '_kwargs_for_hook' 无 history-only 分支
```

## 4. 关联

- [0193 Session Projection Fabric](0193-session-projection-fabric-model-visible.md) — 读 SSOT
- [0196 Convergence 控制面](0196-convergence-control-plane-and-prompt-surface.md) — Delivery gate
- [0185 Model-Visible Event Bus](0185-model-visible-event-bus-alignment.md) — spine header 形态
