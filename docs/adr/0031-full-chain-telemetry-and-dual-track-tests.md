# ADR-0031: Full-chain telemetry + dual-track Team mode tests

## 状态
Accepted

## 背景
Team 九种模式需要可回放的全链路可观测与稳定 CI 测试。业务逻辑不得被可观测实现侵入。

## 决定

### 1. 两层契约（长期稳定）

| 契约 | 角色 |
|------|------|
| `Observability` | **Sink**：`emit_span(TraceSpan)`，Console/JSONL/Multiplex/测试收集器 |
| `Telemetry` | **应用 facade**：`span(name, **attrs)`，不耦合 sink |
| `SpanName` + ATTR_* | 闭集词汇，测试与导出断言唯一事实源 |

### 2. L0 运行时（唯一实现面）

- `bind(observability)`：run 入口安装 ambient `Telemetry`（contextvars，可重入）
- `span(name, **attrs)`：边界发射；未 bind 时落到 `NullTelemetry`（永不 None）
- 关联：`trace_id` / `parent_span_id` 仅由 runtime 管理
- **禁止**业务层持有/传递 Observability；**禁止** `is_bound` 双路径

### 3. 绑定规则

- `TeamOrchestrator.run` / `CognitiveAgent.run` **总是** `bind`（边缘职责）
- hooks / tool / transport / LLM 装饰器 **只** `span`（假定 ambient，或 Null）
- 组合根保证 Team 成员共享同一 Observability 实例

### 4. 双轨测试

- Scripted LLM：默认 CI，拓扑 + 模式不变量
- Real LLM：`real_llm` marker，结构断言 only

## 后果
- 正面：后端可替换；业务视觉干净；父子链路与共享 trace 可断言
- 负面：ambient 依赖 contextvars（与 OTel 一致；测试需经 `bind` 或入口 run）
