# Observability — 四段链（目标态）

> 权威决策：[ADR-0183](../../docs/adr/0183-event-bus-framework-ssot.md) · [ADR-0186](../../docs/adr/0186-session-as-event-ssot.md) · [ADR-0195](../../docs/adr/0195-platform-architecture-convergence.md)

## 第一性原理

**事实只追加一次；一切 UI/OTel/诊断都是 fold 投影。**

```text
Producer (Loop / Boot)
  → FactGateway
    → Session.append
      → *.spine.jsonl
        → Deriver (plugin, pure fold)
          → Exporter (plugin: OTel / Langfuse / SSE / Console)
```

## 三轨 → 单轨（迁移中）

| 轨道 | 状态 | 处置 |
|---|---|---|
| `Session.append` | **SSOT** | 保留 |
| `journal.write` (tool/LLM loop) | 遗留 | 退役 → catalog 事实 |
| `spine_reflector_*` (20 plugins) | 遗留 | 退役 → FactGateway |

## 目录归属

| 段 | 应在 | 不应在 |
|---|---|---|
| Registry | `lca_kernel/events/config/` | `manifest.py` 平行表 |
| Gateway | `lca/loop/fact_gateway.py` | cognition 内 emit |
| Session | `lca/session/` | `plugins/session/runtime` 堆 |
| Deriver | `plugins/observability/deriver/<id>/` | transport handlers |
| Exporter | `plugins/observability/exporter/<id>/` | infrastructure 写盘 |
| 薄端口 | `lca/infrastructure/observability/` | 业务 fold 逻辑 |

## 设计模式

- **Observer**：`Session.observe` → persistence、anomaly  
- **Strategy**：可插拔 Deriver / Exporter  
- **Facade**：FactGateway（统一生产）  
- **禁止**：Projection 反向 append（C7）

## 读代码顺序

1. `lca_kernel/events/config/observability/spine.yaml`  
2. `lca/plugins/session/runtime/session.py` — append  
3. `lca/plugins/session/runtime/spine_hook.py` — instrumentation 入 Session  
4. `lca/infrastructure/observability/spine/derivers/step_tree_accumulator.py` — fold 示例  
