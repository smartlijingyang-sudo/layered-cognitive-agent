# Agent Note: HITL 暂停跨 kernel 重启的惰性恢复

Status: implemented

## Problem

`askUserQuestion` 暂停的 run 把可恢复遍历全部放在进程内 `RunSession` 上。kernel 重启后 registry 清空，前端卡片仍在 Postgres 渲染，但 `POST /runs/<id>/answer` 命中 `run_not_found`。根因有两层：

1. 暂停 run 的会话只存在于内存（registry + `InMemoryStateStore`），磁盘没有可重建的完整事实。
2. `runtime.resume` 依赖进程内 `state_store.load(state_ref)` 与已注入的 `writer` 端口，重启后两者都缺失。

## Decision

在现有 ADR-0191/0195 的 durable transport resume 方向上补齐最小闭环：

1. **暂停时落盘 resume bundle**：`_finish_or_pause` 在 `WAITING_INPUT` 分支调用 `write_resume_bundle`，把 run 身份、approval_request、序列化 resume point 写到 `<run_dir>/resume_bundle.json`（`lca/plugins/transport/webserver/carrier/runs/recovery.py`）。
2. **web-assistant 切到 durable StateStore**：profile patch 启用 sqlite state store（与 `web-standard-continuous.yaml` 基线一致），`AgentState` 随暂停落盘，`runtime.resume` 跨重启可加载。
3. **应答时惰性恢复**：`answer_run` / `_dispatch_resume` 在 session 缺失且 bundle 存在时调用 `restore_waiting_run`，重建 `RunSession`（保留原 run_id/trace_id/plan_ref）、重装配 mode runnable、重跑执行环境、注册回 registry 后走正常 resume 命令。`resume_approval` 关键区不引入 await，保持并发单 resume 不变量。
4. **resume 路径补 writer 绑定**：`CognitiveRuntime.resume` 镜像 `_seed_run_session`，在 `capabilities.writer` 为空时注入 `RunSessionWriter`，使 `memory.derive` 等 think 节点在恢复 run 中可读 `context.runtime.writer`。
5. **结论文本落 session**：resume 结果写入 `session.output`，保证无 step-tree fold 的恢复会话也能经 `persist_terminal_projection` 发布最终回复。

恢复会话不重建 `step_tree_bundle` / `thread_tree_writer`，暂停时的 `journal.json` 作为历史记录不被覆盖。

## Alternatives considered

### 启动时全量恢复所有暂停 run

被拒。需要为每个可能永不回答的 run 常驻资源；惰性恢复只在用户实际回答时付出重建成本，且天然幂等（registry 已有则复用）。

### 让 `resume_approval` 内部直接恢复

被拒。`resume_approval` 的 check-then-act 关键区被 `test_resume_approval_critical_section_never_suspends` 钉死为无 await；恢复上移到 HTTP handler 层，命令层不变。

### 仅持久化 resume point，不换 StateStore

被拒。`runtime.resume` 需要真实 `AgentState`，resume point 只够重建 `StateSnapshot`；不持久化状态仍会 `KeyError: mem://...`。

## Verification

- `tests/plugins/transport/webserver/test_run_restart_recovery.py` 覆盖 bundle 写读、缺失返回 None、已存在复用、无 snapshot 跳过。
- 实机复测：`lca-ops kernel-restart` 后浏览器卡片仍可提交，`run_recovered_from_bundle` 日志出现，最终回复唯一落 Postgres，`message_plugins.intervention` 置 approved，composer 恢复。
- 既有 `tests/transport/test_resume_idempotency.py` / `test_resume_concurrency.py` 通过，`resume_approval` 字节码级无悬挂不变。