# lca/session — 事实平面（Fact Plane）

> **目录宪法：** [platform-directory-architecture.md](../../docs/specs/platform-directory-architecture.md)  
> **决策：** ADR-0186 · ADR-0191 · ADR-0192 · ADR-0195

## 1. 职责

Run 级**唯一 durable 事实**的 append 与 fold 入口。

| 模块（目标） | 职责 | 当前实现位置（迁移中） |
|---|---|---|
| `append.py` | `Session.append` 公共 API | `plugins/session/runtime/session.py` |
| `catalog.py` | `@session_event` 闭集 | `plugins/session/runtime/event_catalog.py` |
| `fold.py` | 纯 fold（derive_messages 等） | `lca_kernel/events/fold.py` + derivers |
| `repair.py` | crash turn repair | `plugins/session/runtime/repair.py` |
| `checkpoint.py` | 三边界 flush policy | `plugins/session/checkpoint_policy/` |
| `bind.py` | run bind、spine hook | `plugins/session/runtime/bind.py` |

## 2. 不负责

- 认知决策（cognition）
- HTTP 路由（transport）
- 控制面 State 单写（Reducer / RunCommitter）
- 投影写回事实（C7）

## 7. 副作用

| 动作 | 后果 |
|---|---|
| `Session.append(event_type, data, …)` | 校验 payload → 追加到本 run 日志（仅此一个生产入口）→ 同步 fire observers（异常 contained，不回滚已 commit 的 append）→ 返回落日志的 `SessionEvent` |
| spine hook（`bind.py`） | 把本 run 的 Session 事件投递到 `<run_id>.spine.jsonl`；未 bind 时不产出 |
| `checkpoint.py` durability barrier | 三个入口（step 边界、模型请求边界、工具结果批次）共享同一形态：`await session.flush()` → 检查 per-listener `FlushResult` → 放行或抛 `CheckpointFailure`；`enabled=False` 时三入口 no-op 放行 |
| `repair.py` | 只在崩溃 turn 追加修复事实；不回写既有事件（仅追加，不可变） |

日志是 append-only：不存在删除或原地修改已提交事件的 API。

## SSOT

```text
Session.append → observers → <run_id>.spine.jsonl
```

Journal 执行平面从 loop 热路径**退役**（ADR-0192）。

## 依赖

- 允许：`contracts`、kernel `events/fold`
- 禁止：`cognition`、`transport`、`plugins`（除 boot 装配）

## 迁移

Wave P1/P4：自 `plugins/session/runtime/` 提升；保留薄 plugin 仅做 Manifest 注册。
