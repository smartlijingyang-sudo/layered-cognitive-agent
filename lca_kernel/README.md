# lca_kernel — 启动与事件机制

> 权威决策：[ADR-0115](../docs/adr/0115-kernel-transport-boundary.md) · [ADR-0183](../docs/adr/0183-event-bus-framework-ssot.md) · [ADR-0195](../docs/adr/0195-platform-architecture-convergence.md)

## 30 秒：Kernel 做什么

Kernel **编译并启动**插件树，**不**执行 Agent 认知，**不**知道 HTTP。

```text
argv / LCA_PROFILE
  → source + resolve (K1)     # Manifest · DAG · 拓扑
  → plan compile (K2)         # CompiledRunPlan
  → run_kernel (K3–K4)      # cordis Fiber · 闭包校验
  → install_observability (K5)
  → lifecycle + env (K6–K7)
  → ctx 交给 transport / CLI
```

## K1–K8 速查

| ID | 模块 | 职责 |
|---|---|---|
| K1 | `source.py`, `resolve.py` | Profile 输入与校验 |
| K2 | `plan.py` | Plan 编译 |
| K3 | `boot.py` | Plugin tree 启动 |
| K4 | `closure.py` | 运行时闭包 |
| K5 | `observability.py` | 观测 registry 装配（不写 run 事实） |
| K6 | `lifecycle.py` | 信号 · fail-loud |
| K7 | `env.py` | 分层 env · 白名单 |
| K8 | `hmr.py` | patch 热重载 |

## 事件机制 SSOT

| 资产 | 路径 |
|---|---|
| EP / category 注册表 | `events/config/observability/spine.yaml` |
| 业务 domain 事件 | `events/config/business/*.yaml` |
| 投递机制 | `events/bus.py`（EnvelopeBus） |
| Payload 类型 | `events/payloads*.py` |
| Fold 原语 | `events/fold.py` |

**规则**：新增 category 只改 yaml + payload 类型 + 测试；不在业务代码硬编码 category 字符串（用 generated/constants 或 registry lookup）。

## 禁止

- import `lca.plugins.transport` / Starlette / uvicorn
- 在 kernel 内 `Session.append` run 事实（boot catalog 除外）
- 第二套 Manifest schema 或平行 EventBus

## 读代码顺序

1. `boot.py` — `run_kernel` 主链  
2. `resolve.py` — profile 如何变成 plugin DAG  
3. `events/registry.py` + `spine.yaml` — 事件授权  
4. `../bundles/base.yaml` — 默认装哪些插件  
