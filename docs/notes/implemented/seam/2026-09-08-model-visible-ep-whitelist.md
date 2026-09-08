# Agent Note: model-visible spine EP 白名单收口 + SpineEventRecord fail-loud

Status: implemented

## Context

[`run_d91b20e29c5a`](../../../traces/runs/run_d91b20e29c5a)（2026-09-08）触发 `ls -la /tmp` 的 run 在 step3 重复调 `runCommand`。journal steps 显示 `step-001` 出现两次（think + perceive）、`step-002`（第二次 perceive）；spine ledger 里有两条 `ep="unknown"` 的事件，payload 是 `spine.llm.request.header.assistant` 的工具调用决策；spine 上没有 `llm.request.header` 之外的 model-visible EP。ADL 0208 + 本 Note 闭环修复。

## Problem

第一性原理：

1. 模型 round-trip 协议（OpenAI-shape）要求 `tool` 消息前必须有对应 `assistant tool_calls` 消息（按 `tool_call_id` 配对）。
2. fold 把 spine events 投回下一轮 LLM messages；assistan t决策消息来源于 `spine.llm.request.header.assistant` 事件。
3. 该事件落 spine 时 `_SPINE_EP_TO_CATEGORY` 表反查 EP 失败，被 fallback 写成 `execution_point="unknown"`。
4. PR-5（ADR-0183）字节布局从 `EventRecord`（带 `__post_init__` 白名单校验）迁到 `SpineEventRecord`（无 `__post_init__` 校验），C11 闭集硬约束被悄悄绕过。
5. fold 拿不到 assistant 决策消息，把 step2 的 tool result 投回 step3 时只有 `role=tool` 孤儿消息，协议层让模型补一轮 tool call。

## Fix

四 SSOT 一致 + 字节布局 fail-loud，**不动 fold 行为**：

| 文件 | 改动 |
|---|---|
| `lca_kernel/events/payloads/spine.py` | `SPINE_EXECUTION_POINTS` 补 `"llm.request.header"` + `"llm.request.header.assistant"`；`_SPINE_EP_TO_CATEGORY` 补对应条目 |
| `lca_kernel/events/spine/runtime.py` | `SpineEventRecord.__post_init__` 恢复白名单校验；`_build_event_record` spine.* category 反查失败改 fail-loud，**非 spine category 保留 "unknown" fallback** |
| `lca_kernel/events/persistence/persistence.py` | `_map_session_event` 同样按 spine.* vs 非 spine category 分流 |
| `tests/architecture/test_spine_ep_yaml_registry.py` | 新增 3 条不变量测试：四 SSOT 一致 / `SpineEventRecord` 拒未知 EP / typed payload 反查 spine.* 失败 fail-loud；退役 `_YAML_SPINE_CATEGORY_WITHOUT_EP_BASELINE = {"spine.llm.request.header.assistant"}`（delete-when 兑现） |
| `docs/adr/0208-model-visible-spine-ep-whitelist.md` | 记录根因 + 修复切片 + 拒绝的反例（不动 fold 行为、不回退 PR-5 字节布局） |

## Alternative considered

- **不动 fold 层**——拒绝理由：fold 的输入条件是"已落盘"，在 fold 兜底"未落盘"会让 fold 边界漂移到事件层。正确做法是事件层先保证落盘，fold 不变。
- **回退 PR-5 `SpineEventRecord` 字节布局**——拒绝理由：PR-5 的 10 字段字节布局是 SSOT，trace_id 字段是有意演进。回退会丢字段。
- **整体替换 `category_to_spine_ep(...) or "unknown"`**——过严，会破坏非 spine category 落盘的旧路径。采用**按 spine.* 前缀分流**的精确改法。

## Verification

修复前 (`run_d91b20e29c5a`):
- total_duration 25.1s;3 steps (think + perceive + perceive 重复);spine `ep=unknown` ×2;`llm.request.header.assistant` EP 不存在

修复后 (`run_fe61a0192c7f`):
- total_duration **7.6s**;3 steps (think + perceive + perceive 收尾，不再调 tool);spine `ep=unknown` ×**0**;`llm.request.header.assistant` EP ×2 (step-001, step-002) 正确落盘
- H7: tool_total=1, tool_success=1, success_rate=1.0（真·只调了一次）
- 测试 6 + 5 = **11/11 passed**（`tests/architecture/test_spine_ep_yaml_registry.py` + `tests/integration/test_model_visible_e2e.py`）

## Limitations

- `run_fe61a0192c7f` doctor H3 仍报 `duplicate step_id: ['step-001']`——这是**存量问题**（多个历史 run 都有），与本次修复无关，已在脑经 ADR/Note 收口前不开 follow-up。
- spine.py 顶层 `SPINE_EXECUTION_POINTS` tuple 仍是 `ADR-0181` 试点 1 + PR-2/3/4/5/6/7 累计 138 个，**尚有部分 EP 只在 YAML 登记**——这是 ADR-0195 O1 的迁移债，不是本次范围。
- `category_to_spine_ep(...) or "unknown"` 的非 spine 路径仍保留（语义保留）；未来若要进一步收紧，需另起 ADR。