# Transport — 承运层（非第二 Runtime）

> 权威决策：[ADR-0115](../../docs/adr/0115-kernel-transport-boundary.md) · [ADR-0195](../../docs/adr/0195-platform-architecture-convergence.md)

## 30 秒：Transport 做什么

Transport **触发 run、绑定 scope、返回 wire DTO**；认知在 `lca/loop/`，事实在 `lca/session/`。

```text
HTTP / CLI / (future MCP)
  → lifespan: kernel.run_kernel()   # 拿 ctx
  → carrier: POST /runs            # LoopDriver → Agent.run()
  → read: GET /runs/{id}/live      # fold Session → SSE（只读）
```

## 读写分离（目标态）

| 目录 | 允许 | 禁止 |
|---|---|---|
| `carrier/` | 触发 run、resume、HIL answer、域 API | Reducer、PhaseExecutor、append 事实 |
| `read/` | fold 投影、SSE、timeline、debug 视图 | 修复 state、写 spine |
| `wire/` | DTO ↔ contracts | 业务规则 |
| `doctor/` | 只读诊断 | 观察面触发控制面副作用 |

## 现状 → 目标映射

| 现路径 | 迁移 |
|---|---|
| `handlers/runs/execute/` | `carrier/runs/` |
| `handlers/runs/lifecycle/` | `carrier/runs/` + `application/` |
| `handlers/runs/observability/` | `read/runs/` |
| `handlers/runs/terminal/` | `read/runs/`（物化 = fold，非写 state） |
| `handlers/runs/session/RunSession` 内存 resume | 退役 → durable `recover_live_agent` |

## Loop 边界

- `loop_drivers.py` 的 `CognitiveRunDriver` **仅**调用 `Agent`/`Team`，不解释 phase graph。
- Session bind 在 `session/builder.py`；append 只在 Loop 机制内发生。

## 禁止

- import `lca.cognition` 做编排（经 application/runtime）
- `Session.append` / `FactGateway` 在 carrier 热路径
- 第二套 runnable 装配平行于 `application/`

## 读代码顺序

1. `lifespan_adapter.py` — kernel 如何进 ASGI  
2. `handlers/runs/execute/loop_drivers.py` — 默认 driver  
3. `handlers/runs/session/builder.py` — run bind  
4. `router.py` + `routes_*.py` — 路由注册  
