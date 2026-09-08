# Agent Note: SurfaceRender WireContract — 模型可见消息的强类型契约落地

Status: implemented

## Problem

`run_20951da435a6`（任务「分析这个文件」）模型陷入 readFile 重复 3 次循环，`ToolLoopBreakerGate` 强制收口，任务失败。debug 定位 5 个断裂点：

| # | 断裂点 | 现象 |
|---|---|---|
| ① | `hook.py` write 端 | `{assistant_content, tool_calls}` 平铺字段, 无 `message` |
| ② | `lifecycle_emit.py` 双写路径 | `_emit_lifecycle_post → complete_model` 在 `if text:` 守卫下跳过 tool_call-only 响应 |
| ③ | `fold.py` 识别 | 正确 — 无问题 |
| ④ | `messages.py` 读端 | 读 `data["message"]` 找不到 `assistant_content`, 返 None |
| ⑤ | `event_translator.py` transport | `_spine_llm_header_assistant` 在空 content 时返 None, 忽略 `tool_calls` |

5 个文件各自维护「OpenAI message 形状是什么」的理解, 字段名不一致。**根因诊断**: 整个 LCA 缺一套「内部状态 ↔ 外部协议」的强类型契约 + 显式 dispatch + 静态拓扑机制。同模式 bug 在 LCA 多处复发（action dispatch / reducer method / phase routing / EventTranslator / tool invocation / fact shape / skill descriptor）。

## Decision

落地 [ADR-0205 WireContract 元机制](../adr/0205-wire-contract-as-plugin-seam.md) 的 P0 第 1 应用域 — surface render WireContract:

**核心组件**:
1. `lca_kernel/contracts/wire/contracts/model_openai.py` — `OpenAIUserMessage` / `OpenAIAssistantMessage` / `OpenAIToolMessage` / `OpenAIToolCall` / `OpenAIFunction` (Pydantic frozen, `extra="forbid"`)
2. `lca_kernel/contracts/wire/contract.py` — `WireContract` Protocol + `WireContractRegistryMiss` (fail-loud)
3. `lca_kernel/contracts/wire/registry.py` — `WireRegistry` profile-scoped, 禁用 process global
4. `lca_kernel/contracts/wire/violations.py` — `WireContractViolation` + 写 `wire.contract.violation.v1` spine event
5. `lca_kernel/contracts/wire/transport.py` — `WireTransport` Protocol
6. `lca_kernel/contracts/wire/config/observability/surface_render.yaml` — SSOT 描述 (wire contract key → surface type → transport)

**ModelVisibleUnit 扩展** (随 [ADR-0193](0193-session-projection-fabric-model-visible.md)):
- 新增 `wire_view(event) -> OpenAIMessage | None` 第 4 步, 委托 `WireRegistry.get(key).extract(event_data)`
- `view()` 保留, 不破坏 `I-MV-PROJ-*` 不变量

**写端改造**:
- `capture_post_llm` 用 `OpenAIAssistantMessage.construct(content, tool_calls)` 强类型构造
- 删除 `assistant_content` / `tool_calls` 平铺字段 (同 PR)

**双路径合并**:
- `complete_model` 不再写 surface, 只写 catalog `assistant.responded.v1`
- 唯一 surface 写入路径 = `capture_post_llm`

**读端零分支**:
- `derive_event_message` → `unit.wire_view(event).model_dump()`
- 删除 30 行 if/elif (同 PR)

**Transport 收口**:
- `_spine_xxx` 5 处硬编码 → `_TRANSPORT_TABLE` 派发, 委托 `WireTransportRegistry.get("sse.chunk").render(msg)`

**Plugin 扩展点**:
- `@plugin wire.contract.claude_cache` Manifest 声明 `base: openai.assistant` + `extra_fields.cache_control`, Resolve 拓扑校验无环

## Alternatives considered

- **新 EP `assistant.message.observed`**（平行 spine 事件）: 否决 — 平行事实源, 与 ADR-0193 surface fold 重复。
- **改 `derive_event_message` 为 N 个策略类**（每个 surface 一个 class）: 否决 — 收归 `WireContract` 一个 Protocol, 避免无限细分。
- **复用 `ControlSlot` 11 闭集**: 否决 — 宪法级闭集, 加 slot 需 ADR, 不应混入 WireContract。
- **复用 `EventRegistry` 鉴权矩阵**: 否决 — events 是 pub/sub 鉴权语义, wire 是 dispatch 语义, 混淆破坏两层职责。
- **过程全局单例** (`get_surface_render_plan()`): 否决 — 与 ADR-0194/0195 profile-scoped 原则冲突, 易引入隐性依赖。
- **平铺字段保留兼容** (`assistant_content` 加 deprecated 注脚): 否决 — AGENTS.md 明确「无 delete-when 的兼容分支 = 红灯」, 同 PR 全删。
- **一次性迁移**（直接重写 if/else）: 否决 — 9 阶段切分（纯加法骨架 → 双轨 → 替换 → transport 收口）, 永不一次性。

## Consequences

**正面**:
- 任何新 wire shape 改 Pydantic 一处, 全栈联动
- 字段名/形状定义有 SSOT, 写端和读端不再各自维护
- 5 类 seam (model/tool/fact/skill/provider) 同元机制, 推广到 P1 仅是新增 Contract
- plugin 扩展走 Manifest `wire.contract.provides`, Resolve 拓扑校验
- 架构测试 fail-loud (WC-1 ~ WC-8 + MV-*), 错配立即暴露

**约束**:
- 写端不允许 dict 字面量构造 message, 必走 `OpenAI*Message.construct()`
- dispatch 入口不允许 if/elif 散落 (架构测试 fail-loud)
- Registry miss 抛 `WireContractRegistryMiss`, 不静默 None
- WireContract 违反必写 `wire.contract.violation.v1` spine event

**长期**:
- 同模式 bug (action dispatch / reducer method / phase routing / EventTranslator / tool invocation / fact shape / skill descriptor) 在后续 P1 PR 各自走 WireContract 落地, 一次性元机制覆盖

## Verification

**架构测试**（fail-loud, 11 条）:
- `tests/contracts/wire/test_wire_contract_registry.py` — Registry 完整性
- `tests/contracts/wire/test_openai_message_contract.py` — Pydantic schema 校验
- `tests/lca_kernel/events/test_wire_view.py` — `unit.wire_view` roundtrip
- `tests/plugins/events/hooks/model_visible/test_assistant_message_shape.py` — 写端 shape
- `tests/integration/test_assistant_surface_unicity.py` — 唯一写路径
- `tests/lca_kernel/events/test_parity_old_vs_new.py` — parity test
- `tests/coordinator/test_transport_slot_dispatch.py` — Transport table 覆盖
- `tests/plugins/model/test_anthropic_claude_plugin.py` — plugin override
- `tests/architecture/test_no_wire_ifelse.py` — no if/elif in dispatch
- `tests/architecture/test_wire_contract_invariants.py` — WC-1 ~ WC-8 fail-loud
- `tests/architecture/test_manifest_provides_complete.py` — Manifest 声明完整

**端到端**: 重跑 run_20951da435a6 场景, 不再陷入 readFile 循环。

**架构不变量** (11 条 fail-loud):
- MV-SLOT-1, MV-SLOT-2, MV-SHAPE-1, MV-ROUNDTRIP-1, MV-TRANSPORT-1, MV-PARITY-1, MV-UNICITY-1, MV-DICT-1, MV-IFELIF-1
- WC-3 (overrides DAG 无环), WC-4 (Manifest provides 完整)

## Status / next steps

P0 实施中 (9 PR, [ADR-0204 §9](../adr/0204-surface-render-slot-plan-strategy.md))。完成后 P1 推广:
- P1-PR-10: Tool Invocation WireContract (`ToolInvocationEnvelope` / `ToolResultEnvelope`)
- P1-PR-11: Fact Shape WireContract (`FactPayload`)
- P1-PR-12: Skill Descriptor WireContract (`SkillManifest` / `SkillEntrypoint`)
