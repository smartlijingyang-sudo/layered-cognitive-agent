# plugins/session — Session runtime 与投影 plugin

事实平面 SSOT 在 [`lca/session/`](../../session/README.md)。本目录保留 `bundles/session-runtime.yaml` 装配的薄 plugin（runtime store、投影、标题、遥测）。

| 家族 | Bundle `$module` 前缀 | 说明 |
|---|---|---|
| runtime | `lca.plugins.session.runtime.plugin.plugin` | `session.store`（SessionStore + DSH Session） |
| checkpoint | `checkpoint_policy` | 三边界 flush policy |
| projection | `projection_*`, `session_*`, `token_usage` | DSH 投影 fold |
| title | `title_service` | 标题服务（`title_llm_provider` 按部署选挂） |
| telemetry | `telemetry_*` | 捕获 + OTel（bundle 默认 DISABLED） |

**Bundle SSOT:** [`bundles/session-runtime.yaml`](../../../bundles/session-runtime.yaml) — 每条 `$module` 须可 `importlib` 加载且暴露 `setup`。

## 1. 职责

`bundles/session-runtime.yaml` 装配的薄 plugin：SessionStore + DSH Session 的
runtime store、DSH 投影 fold、标题服务、遥测捕获与 checkpoint policy。

## 2. 不负责

- 事实平面 API 本体（append / catalog / fold / repair / bind / recovery 在
  [`lca/session/`](../../session/README.md)，Wave P1/P4 迁移目标）
- 认知决策与图遍历

## 7. 副作用

| 家族 | 后果 |
|---|---|
| `runtime` | 装配期注册 `session.store` capability；run 期的 durable 写仍只经 `Session.append` 单入口 |
| `checkpoint_policy` | 三个边界触发 `await session.flush()`，失败抛 `CheckpointFailure`；`enabled=False` 时 no-op |
| `telemetry_*` | 默认 DISABLED；启用后外发 OTel，队列满丢弃本批（不回滚已 commit 的 append） |
| `title_service` / `title_llm_provider` | 生成标题属读侧派生；LLM 失败按 contained 处理并保留回退标题，不阻塞主响应、也不写事实 |

## 3. 输入

装配期：`bundles/session-runtime.yaml` 的 `$module` 与 Config（store 后端选择、
checkpoint 开关）；run 期：注入的 `Session` / DSH log、事件序列、
`AgentState` 引用与 LLM 适配器（标题服务）。

## 4. 输出

注册的 capability（`session.store` 等）、DSH 投影 fold 结果
（model-visible / stats / turn control 视图）、checkpoint 的 `FlushResult` 列表、
telemetry 的 OTel 导出批次。事实本身不在此层定义——写入口是 `lca.session`。

## 5. 允许依赖

`lca.contracts`、`lca_kernel.events`、`lca.plugins`、`lca.harness`、
`lca.infrastructure`、`lca.session`，第三方 `opentelemetry.*`。
（现状计数 75 / 29 / 15 / 14 / 10 / 8。）

## 6. 禁止依赖

`lca.agent`、`lca.application`、`lca.cognition`、`lca.loop`、`lca.runtime`、
`lca.nodes`（当前零 import）。plugin 不得自带第二套事实写入口：durable 写只能经
`Session.append`。

## 8. 失败语义

按源码 `raise` 统计：`ValueError` 42、`TypeError` 10、`SessionLogReadError` 7、
`SessionForkError` 6、`CheckpointFailure` 2、`JournalWriteError` 2、
`RuntimeError` 1。checkpoint 失败上抛 `CheckpointFailure`（不静默放行）；
观测/遥测队列满时丢批次并计数，已 commit 的 append 不回滚；日志读失败抛
`SessionLogReadError` 而非返回空投影。

## 9. 公共入口

包门面不重导出符号（__all__ 为空）。装配以 bundle 的 `$module` 路径为准：
`runtime/plugin.py`、`checkpoint_policy/`、`projection_*`、`session_*`、
`title_service/`、`title_llm_provider/`、`telemetry_*`；每条须可 importlib 加载且
暴露 setup。
## 迁移

Wave P1/P4/P5-02：事实 API（append / catalog / fold / repair / bind / recovery）→ `lca.session`；runtime 子模块目录化（`bus/facade.py`、`spine/hook.py` 等）。

**delete-when（整目录收敛）：**

- `bundles/session-runtime.yaml` 无 `lca.plugins.session.runtime` 条目
- `rg "from lca.plugins.session.runtime.(session|event_catalog|repair|bind|recovery|fold|checkpoint) import" lca/ tests/` 无命中
- `rg "from lca.plugins.session.runtime.(bus.bus_facade|log.log_reader|cursor.cursor_port|spine.spine_hook|spine.spine_event_projection|resume.resume_point) import" lca/ tests/` 无命中
- runtime plugin：`$module` 已指向 `runtime.plugin.plugin`
