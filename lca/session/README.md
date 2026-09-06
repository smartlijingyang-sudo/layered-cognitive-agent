# lca/session — 事实平面（Fact Plane）

> **目录宪法：** [platform-directory-architecture.md](../../docs/specs/platform-directory-architecture.md)  
> **决策：** ADR-0186 · ADR-0191 · ADR-0192 · ADR-0195

## 职责

Run 级**唯一 durable 事实**的 append 与 fold 入口。

| 模块（目标） | 职责 | 当前实现位置（迁移中） |
|---|---|---|
| `append.py` | `Session.append` 公共 API | `plugins/session/runtime/session.py` |
| `catalog.py` | `@session_event` 闭集 | `plugins/session/runtime/event_catalog.py` |
| `fold.py` | 纯 fold（derive_messages 等） | `lca_kernel/events/fold.py` + derivers |
| `repair.py` | crash turn repair | `plugins/session/runtime/repair.py` |
| `checkpoint.py` | 三边界 flush policy | `plugins/session/checkpoint_policy/` |
| `bind.py` | run bind、spine hook | `plugins/session/runtime/bind.py` |

## 不负责

- 认知决策（cognition）
- HTTP 路由（transport）
- 控制面 State 单写（Reducer / RunCommitter）
- 投影写回事实（C7）

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
