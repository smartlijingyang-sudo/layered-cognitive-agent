# Transport — 承运层（非第二 Runtime）

> 权威决策：[ADR-0115](../../docs/adr/0115-kernel-transport-boundary.md) · [ADR-0195](../../docs/adr/0195-platform-architecture-convergence.md) · [platform-directory-architecture.md](../../docs/specs/platform-directory-architecture.md)

## 1. 职责

承运层：触发 run、绑定 run scope、把 Session / spine 事实折叠成 wire DTO 返回。
三个子平面分工固定——`webserver/carrier/` 写路径（触发）、`webserver/read/`
读路径（折叠）、`webserver/wire/` DTO 适配。

## 2. 不负责

- 认知循环（`lca/loop/`）与事实定义（`lca/session/`）
- 第二 Runtime：transport 不解释 phase 图、不做状态修复、不写控制面 State
  （见下文「禁止」）

## 7. 副作用

| 子平面 | 后果 |
|---|---|
| carrier | run 未被认知路径关闭时，经 `emit_carrier_run_failed` 向 `Session.append` 追加一条终态事实；已有终态事件时不重复追加 |
| carrier | 启动 driver 任务；真正的世界副作用仍经 Command / Approval 控制面 |
| read | `runs/terminal/failure` 创建 `traces/runs/<run_id>/` 并追加 `kernel.log`；live SSE 只订阅 `session.tail` |
| wire | 无：只做 DTO ↔ contract 转换 |

## 30 秒：Transport 做什么

Transport **触发 run、绑定 scope、返回 wire DTO**；认知在 `lca/loop/`，事实在 `lca/session/`。

```text
HTTP / CLI / (future MCP)
  → lifespan: kernel.run_kernel()   # 拿 ctx
  → carrier: POST /runs            # LoopDriver → Agent.run()
  → read: GET /runs/{id}/live      # fold Session → SSE（只读）
```

## 读写分离（P3 目标态）

| 目录 | 允许 | 禁止 |
|---|---|---|
| `webserver/carrier/` | 触发 run、resume、HIL answer、域 API | Reducer、PhaseExecutor、append 事实 |
| `webserver/read/` | fold 投影、SSE、timeline、debug 视图 | 修复 state、写 spine |
| `webserver/wire/` | DTO ↔ contracts | 业务规则 |
| `webserver/doctor/` | 只读诊断 | 观察面触发控制面副作用 |

## 现状 → 目标映射

| 现路径 | 迁移 |
|---|---|
| `handlers/runs/execute/` | `carrier/runs/execute/` ✓ P3-02 |
| `handlers/runs/lifecycle/` | `carrier/runs/lifecycle/` ✓ P3-04 |
| HIL resume | `carrier/runs/resume.py` ✓ P3-05（`recover_live_agent` 权威） |
| `handlers/runs/observability/` | `read/runs/`（P3-07） |
| `handlers/runs/terminal/` | `read/runs/`（P3-08） |
| `handlers/runs/wire/` | `wire/`（P3-11） |
| `RunSession.snapshot/runnable` | 进程内 cache，非 SSOT ✓ P3-06 |

Legacy `handlers/runs/*` 保留 COMPAT shim，delete-when：`rg handlers/runs/(execute|lifecycle)` 生产 import = 0。

## Loop 边界

- `carrier/runs/execute/loop_drivers.py` 的 `CognitiveRunDriver` **仅**经 `CognitiveRunnableAssembler` 组装后调用 `Agent.run()` / `Team.run()`。
- Session bind 在 `session/builder.py`；append 只在 Loop 机制内发生。

## 禁止

- import `lca.cognition` 做编排（经 application/runtime）
- `Session.append` / `FactGateway` 在 carrier 热路径
- 第二套 runnable 装配平行于 `application/`

## 读代码顺序

1. `lifespan_adapter.py` — kernel 如何进 ASGI  
2. `carrier/runs/execute/loop_drivers.py` — 默认 driver  
3. `carrier/runs/resume.py` — durable resume 门控  
4. `handlers/runs/session/builder.py` — run bind  
5. `router.py` + `routes_*.py` — 路由注册  
