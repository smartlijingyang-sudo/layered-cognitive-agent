# LCA 核心插件化重构 — 对齐 DSH 架构

> **原则：每个核心能力是一个独立可替换插件，通过 seam 注册，逻辑自包含。**

## 问题

LCA 的核心能力（session 管理、prompt 装配、agent 生命周期）不是插件，而是嵌在 layer 模块里的硬编码逻辑。DSH 的每个核心能力是一个独立 `packages/core/xxx/` 插件，通过 `ctx` seam 注册，可替换。

## 已有插件（薄包装，待加强）

| 插件 | seam | 状态 |
|---|---|---|
| `llm_service` | `llm` | ✅ 薄包装 |
| `tools_service` | `tools` | ✅ 薄包装 |
| `memory_service` | `memory` | ✅ 薄包装 |
| `loop_cognitive` | `agent_loop` | ✅ 有实际逻辑 |
| `loop_dsh_bridge` | `agent_loop` | ✅ 有实际逻辑 |
| `seam_definitions` | — | ✅ 纯声明 |

## 本次新增核心插件

### 1. `session_service` — Session 事件溯源 + 投影

**seam:** `session_service`
**职责:**
- 提供 `derive_messages()` — 从 session events 投影 LLM 消息历史
- Surface 事件类型定义（哪些 event 产出 LLM 可见消息）
- `AssistantResponded` 事件类型
- Session 创建 / 管理

**对齐 DSH:** `packages/core/session/` — `SessionStore` + `deriveMessages()` + `SurfaceManager`

### 2. `system_prompt` — 组合式 Prompt 装配

**seam:** `system_prompt`
**职责:**
- Section 注册表（name + order + text，可叠加）
- Context 注册表（动态运行时上下文）
- Variable 注册表（`{{name}}` 严格插值）
- Waterfall 装配钩子
- `assemble()` → `render()` 两阶段

**对齐 DSH:** `packages/core/system-prompt/` — `SystemPrompt` service + `PromptSection` + `renderPrompt()`

### 3. `agent_service` — Agent 生命周期事件记录

**seam:** `agent_service`
**职责:**
- 在 session log 中记录 turn/step 边界事件
- 记录 assistant 响应（`AssistantResponded`）
- 记录 tool call/result
- 类型安全的 event recording facade

**对齐 DSH:** `packages/core/agent-loop/` — `ReactLoopAgent` 内部 session.append() 调用

## 插件规范

每个插件遵循：
```python
# lca/plugins/xxx/__init__.py
from lca.contracts.harness.plugin import PluginKind, PluginManifest

manifest = PluginManifest(
    id="lca.xxx",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.SERVICE,
    provides=("seam_key",),
)
name = "lca.xxx"

def apply(ctx, config):
    service = XxxService()
    ctx.mount("seam_key", service)
```

关键约束：
- 逻辑在插件里，不在 layer 模块里
- 通过 seam 注册，可被替换
- 依赖通过 `requires=` 声明
- disposer 模式：注册返回 disposer 供卸载

## 后续 Phase（本次不做）

- Phase 4: runtime loop 改用 `agent_service` 记录事件
- Phase 5: reasoner 改用 `system_prompt` 装配 prompt
- Phase 6: `CognitiveLiveAgent` 改用 `session_service.derive_messages()`
- Phase 7: 清理旧代码
