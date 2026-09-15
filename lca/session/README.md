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

## 3. 输入

`Session` 构造参数（run id、catalog 事件类型）、`append` 的 payload 与 producer、
bind/recover/repair 所需的事件序列与 `ResolvedProfile` 元数据；持久化后端由
`lca_kernel.events` 与 `lca.infrastructure` 的 sink/store 注入，本层不自行开连接。

## 4. 输出

包门面模块级 __all__ 共 32 个符号：事实入口（`Session`、
`known_session_event_types`、`validate_event_type_for_read`、
`append_approval_resolved_if_pending`）、run 绑定
（`RunEventSessionBridge`、`BoundRunEventSession`、`EventSessionBinder`、
`bind_run_event_session*` / `unbind_run_event_session`、
`event_session_binder_from_scope`）、恢复与修复（`recover_live_agent`、
`recovery_from_events`、`repair_interrupted_turn`、
`sync_run_status_from_recovery`、`assert_resume_allowed`）、durability
（`SessionCheckpointPolicy*`、`FlushableSession`、`CheckpointFailure`）、读侧 fold
（`foldSurface`、`foldRequestHeader`、`canonicalHeader`、`headerEquals`）与错误
（`SessionRecoveryError`、`SessionRepairError`、`UnknownSessionEventTypeError`）。

## 5. 允许依赖

`lca.contracts`、`lca_kernel.events`、`lca.infrastructure`；迁移期还包含
`lca.plugins`（runtime store 与 checkpoint policy 的现址）与 `lca.runtime` 各一处
import——见 §6 的收敛条件。

## 6. 禁止依赖

`lca.agent`、`lca.application`、`lca.cognition`、`lca.harness`、`lca.loop`。
事实平面不得反向依赖认知或组合根；`lca.plugins` / `lca.runtime` 的现存边只随
Wave P1/P4 收敛消失（README「迁移」节的 delete-when）。

## 8. 失败语义

按源码 `raise` 统计：`SessionRecoveryError` 12、`TypeError` 6、`ValueError` 5、
`SessionRepairError` 3、`SessionReentryError` 1、`UnknownSessionEventTypeError` 1。
不可恢复的输入错误直接抛类型化异常，不静默降级；observer 异常 contained，
已 commit 的 append 不回滚；`waiting_input` 的 run 必须恰好有一个未解决 approval，
否则恢复即失败（AGENTS.md §4）。

## 9. 公共入口

包门面与模块 __all__ 声明一一对应（32 项）：

`REQUEST_HEADER_CATEGORY`, `SURFACE_ASSISTANT_TYPE`, `SURFACE_TOOL_RESULT_TYPE`, `TOOL_NOT_STARTED`, `TOOL_OUTCOME_UNKNOWN`, `BoundRunEventSession`, `CheckpointFailure`, `EventSessionBinder`, `FlushableSession`, `RunEventSessionBridge`, `Session`, `SessionCheckpointPolicy`, `SessionCheckpointPolicyProtocol`, `SessionRecoveryError`, `SessionRepairError`, `UnknownSessionEventTypeError`, `append_approval_resolved_if_pending`, `assert_resume_allowed`, `bind_run_event_session`, `bind_run_event_session_from_store`, `canonicalHeader`, `event_session_binder_from_scope`, `foldRequestHeader`, `foldSurface`, `headerEquals`, `known_session_event_types`, `recover_live_agent`, `recovery_from_events`, `repair_interrupted_turn`, `sync_run_status_from_recovery`, `unbind_run_event_session`, `validate_event_type_for_read`
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

见 §5 / §6：允许与禁止清单与 pyproject `[tool.lca.package_contracts.lca.session]` 镜像。

## 迁移

Wave P1/P4：自 `plugins/session/runtime/` 提升；保留薄 plugin 仅做 Manifest 注册。
