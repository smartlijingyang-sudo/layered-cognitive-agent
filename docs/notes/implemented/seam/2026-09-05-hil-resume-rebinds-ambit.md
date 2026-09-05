# Agent Note: HIL resume 必须重绑 RunAmbit —— askUserQuestion 恢复链路的 ambient 真值

Status: implemented

> 本 Note 钉「human-in-the-loop（askUserQuestion）暂停 → `/runs/{id}/answer` 恢复」
> 这条链路的 ambient 边界：恢复的 turn 与首次 execute 的 turn 需要同一份
> ``RunAmbit``（FileStore / workspace / plane bindings），否则恢复侧的 prompt
> 渲染拿不到 FileStore。

## Problem

`askUserQuestion` 抛 `ApprovalPendingError` 使 run 进入 `waiting_input`。
`POST /runs/{id}/answer` 触发 `RunLifecycleCoordinator.resume()`。修复前
`resume()` 只重绑 `plane_bindings_scope`，未重绑 `RunAmbit`；恢复的 think 在
`render_system_role` 里经 `current_file_store()` 读到 `None`，抛
`RuntimeError("no FileStore in ambient scope")`，run 直接 failed。

## 接缝边界（谁拥有真值）

- **execute 侧**（`RunExecutionEnvironment.prepare()`）是唯一解析 providers 并
  构造 `RunAmbit` 的地方；构造后把快照存到 `session.ambit`。
- **resume 侧**（`RunLifecycleCoordinator.resume()`）不重新解析 providers（无
  ctx），只从 `session.ambit` 重绑：`bind_run_ambit(ambit)` +
  `run_workspace_scope(run_id)` + `plane_bindings_scope(bindings)`。
- `RunSession.ambit` 是跨暂停的 ambient 真值载体；它 immutable（frozen
  dataclass），重绑安全。

## 不变量

1. 任何「暂停后恢复」的执行路径，进入 `runnable.resume` 前必须重绑
   `RunAmbit`（至少 FileStore），与 execute 侧同一快照。
2. 新增 ambient 资源只加到 `RunAmbit` 字段（ADR-0122），不在 resume/execute
   各自加 `with` 块。

## 前端投影（LobeHub）

- 暂停信号 = journal `AgentRunFinished` 的 `status: "input-required"`；问题
  内容不在 journal 流，而在 `GET /runs/{id}` 快照的 `approval_request.questions`。
- `LcaRunDriver` 收到 input-required 后取快照、创建
  `lobe-user-interaction/askUserQuestion` tool 消息并写入
  `pluginState.lca = { run_id, status }`；renderer 复用
  `@lobechat/shared-tool-ui/ask-user` 组件，提交时 `POST /runs/{id}/answer`。
- 渲染器注册需在 `src/spa/initialize/toolSurfaces.ts` 调
  `ensureLcaToolRenderRegistered()`（patch 接入）。

## Alternatives considered

- **resume 侧重新解析 providers（传 ctx 进 resume_approval）**：需要把 ctx 穿过
  `resume_approval → resume_run → resume` 的协议链，改动面大且 resume 本不应依赖
  carrier ctx；否决。
- **只重绑 FileStore（不存整个 ambit）**：能修当前崩溃，但后续 ambient 资源
  （workspace / assistant_id）仍会缺；存整个 `RunAmbit` 一次到位，符合 ADR-0122
  「ambient 只加字段」；采用存 ambit。

## 回归锁

`tests/transport/test_resume_rebinds_ambient.py` 断言 `resume()` 内
`current_file_store()` 返回 `session.ambit.file_store`。
