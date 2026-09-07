# Agent Note: Tool Result Prompt Closure — ADR-0193 写面 + 交付/观测 sibling

Status: implemented

## Problem

`run_640c492b7f40`（任务「分析下这个文件」）三步 think 循环中 LLM 每轮 `role=tool` 计数为 0；模型反复重提取 PDF。并行问题：Reflect 批部分成功记成全失败；Delivery gate 把长 stdout 当已交付；spine `llm.request.header` 只记 pre-merge kwargs。

## Decision

补全 ADR-0193 **写面**（不新增 EP）：

- `commit_body_tool_execute_end` → `append_tool_result_surface` with `surfaceOp=append` + OpenAI-shaped `data.message`
- 读路径不变：`assemble_model_history` → `openai_messages_with_history`

Sibling：

- `task_requires_synthesis(task)` — 分析/总结类任务不把 tool stdout 当 delivery
- `ModelVisibleHookAdapter._kwargs_for_hook` — merge `prompt + history` 与 chat adapter 一致

## Alternatives considered

- **新 EP `tool.result.observed`**：否决；平行事实源，与 0193 surface fold 重复。
- **Brain 读 `retrieved_context`**：否决；绕过 Session SSOT。
- **改 `format_prior_conversation`**：否决；污染 GeneralChat 语义。

## Verification

- `tests/infrastructure/session/test_tool_result_surface.py`
- `tests/loop/test_tool_surface_commit.py`
- `tests/cognition/test_critic_partial_batch.py`
- `tests/cognition/test_delivery_analysis_task.py`
- `tests/plugins/events/hooks/model_visible/test_adapter_wire.py`

## Consequences

- `tool_result_message.py` / `tool_surface_emit.py` 为 infrastructure 投影 + emit seam
- Delivery gate 对 synthesis task 需 artifacts 或模型 RESPOND，不能 raw dump 短路
- debug-run grep `llm.request.header` 可见 `role=tool`
