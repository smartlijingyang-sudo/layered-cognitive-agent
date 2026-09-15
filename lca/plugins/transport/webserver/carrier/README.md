# Transport carrier — write path

> ADR-0195 §2.4 · [platform-directory-architecture.md](../../../../docs/specs/platform-directory-architecture.md)

## 1. 职责

**Carrier** triggers runs and domain commands: POST run scheduling, the run
lifecycle coordinator, durable HIL resume.

## 2. 不负责

It does not fold projections or interpret phase graphs. It appends a Session
fact only on the one path below.

| Subpath | Responsibility |
|---|---|
| `runs/execute/` | POST run scheduling, loop drivers, execution environment |
| `runs/lifecycle/` | Run lifecycle coordinator, runnable assembly |
| `runs/resume.py` | Durable HIL resume (`recover_live_agent` authority) |
| `runs/answer.py` | *(future)* HIL answer wire |
| `assistants/` | *(future)* assistant domain API |

## 7. 副作用

| 入口 | 对外后果 |
|---|---|
| `runs/lifecycle` 失败收敛 | 当认知路径没有关闭 run 时，经 `emit_carrier_run_failed` 向 **`Session.append`** 追加一条 `RuntimeObserved(run.lifecycle.failed)` 终态事实（SSOT 单轨，无 journal 回退）；同一 run 已有终态事件时不重复追加 (`journal_has_terminal_event`) |
| `runs/resume` | 恢复并重新绑定 run 本地 Session scope；不 checkpoint `working` 状态 |
| 触发 run | 启动 driver 任务；控制面后果全部经 Command / Approval，不由 carrier 直接执行副作用 |
| `composio/` | *(future)* composio domain API |

Legacy `handlers/runs/execute/` and `handlers/runs/lifecycle/` re-export from here until P5 shim deletion.
