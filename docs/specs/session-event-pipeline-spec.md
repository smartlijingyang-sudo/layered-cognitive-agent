# Session 事件链路规格:发射 → 落盘 → 消费

> Status: 现行规范。事件真值层形态由 [ADR-0186](../adr/0186-session-as-event-ssot.md) 锁定;
> 本规格描述该真值层之上的持久化、消费链路,以及四个职责模块的插件化组织。
> 事件词表归 [harness-spine-spec](harness-spine-spec.md) §2.2.3;Journal/Spine 归
> [architecture-overview](../observability/architecture-overview.md);
> model-visible 生产语义归 ADR-0185。

## 1. 一句话

Session 事件流是唯一事实:`Session.append` 是唯一写入口,持久化模块是唯一写盘者,
投影/标题/遥测三个消费模块只从已提交事件派生,全部以可插拔插件形态挂载。
排查任何事件先问:它是运行时总线事件、Session 持久事件,还是一次提交通知?

## 2. 链路总览

```text
【发射面】                  【持久化模块】                        【消费面】
认知循环 / 插件             session-persistence                  投影 / 标题 / 遥测
      │                           │                                   ▲
      ▼                           ▼                                   │
 Session.append(type, data) ─► log.push(event)  [in-process SSOT]     │
      │  校验 + 冻结 + 拒重入      │                                   │
      │                           ├─► SessionObserver 同步通知 ────────┤ (投影/遥测订阅)
      │                           │    (失败 contained,不反噬 append)  │
      │                           ▼                                   │
      │                  per-session write-behind 控制器               │
      │                  首条事件开固定窗口 → 批量写                    │
      │                           │                                   │
      │                           ▼                                   │
      │                  JSONL 后端(每 session 一个工件)              │
      │                  批量追加 + 每批一次 fsync                     │
      │                           │                                   │
      │                  <sessions>/<session_id>.session.jsonl        │
      │                                                               │
      └─ Session.flush():下一动作前的显式排空(顺序 + 错误检查点)      │
                                                                      │
 标题事件 ──────────── 也经 Session.append 回到日志 ───────────────────┘
```

链路方向单向:发射 → 提交 → 通知 → 批量落盘 → (崩溃后)恢复 → 派生消费。
任何消费模块不得反向写事实;标题产生的事件通过唯一写入口回到日志。

## 3. 事件三分类(先分类,再谈链路)

| 类别 | 形态 | DSH 对照 | LCA 现状 | 是否落盘 |
|---|---|---|---|---|
| 运行时总线事件 | 实时协作、拦截、改写、策略控制 | Cordis `ctx.emit/on/waterfall`(`agent/request`、`tools/pre-execute` 等),**不**进 Session 日志 | spine EventBus 类别(`lca_kernel/events/config/observability/spine.yaml`) | DSH:否;LCA:是 → `<run_id>.spine.jsonl`(Journal 平面,正按 ADR-0186 向 Session 平面收敛) |
| Session 持久事件 | 可恢复、可重放、可审计的事实 | `SessionEventMap` 闭集(`user/message`、`assistant/message`、`tool/call`、`turn/start` 等) | `@session_event` 词表(`lca/contracts/harness/memory/events.py`,23 种) | 是 → `*.session.jsonl` |
| 提交/持久化通知 | 「某条事件已提交」的路由信号 | `session/event`、`session/flush`——本身**不是**日志记录 | `SessionObserver`、`FlushListener` | 通知自身不落日志 |

判定规则:一个事实若必须在重启后仍存在,它是 Session 持久事件;
若只用于进程内协作/拦截,它是运行时总线事件;若只是「已提交」的信号,它是通知。
**「发出事件」≠「记录到日志」**:只有经 `Session.append` 成功提交的才是事实。

### 3.1 事件词表分组(Session 平面)

| 组 | 作用 | LCA 代表 |
|---|---|---|
| 回合边界 | 标记一次用户驱动的完整回合;即使没有模型步骤也留下边界事实 | `turn.started.v1` / `turn.ended.v1` |
| 步骤边界 | 一步 = 一次模型请求及其触发的执行 | `step.started.v1` / `step.ended.v1` |
| 模型表面 | 参与模型消息历史派生(surface) | `message.accepted.v1`、`assistant.responded.v1`、`context.injected.v1` |
| 执行与重建 | 失败尝试、审批、恢复所需的上下文状态 | `model.requested/completed/failed.v1`、`thinking.delta.v1`、`approval.persisted/resolved.v1`、`session.checkpoint.v1`、`inbox.spliced.v1` |

### 3.2 三档可见性:模型表面 / log-only / 瞬时帧

- **模型表面事件**:参与 fold 派生模型下一次请求的消息历史。
  DSH `deriveMessages()`;LCA `foldRequestHeader` / surface fold
  (`lca_kernel/events/fold.py`、`observability/replay/fold_source.py`)。
- **log-only 事件**:可审计、可重放,但不进模型历史(DSH `assistant/chunk`
  在派生中被跳过、结算消息权威;LCA `thinking.delta` 等按词表 visibility 标注)。
- **瞬时帧**:传输层实时流(SSE chunk、进度推送),低延迟 UI 用,
  **不构成可恢复事实**;最终结算必须落成模型表面事件或 log-only 事件。

不变量(ADR-0185 / DSH 同款):**model-visible ⟺ logged**——模型看到的任何输入
都必须能从 Session 日志重建;绕过日志直塞模型上下文即违反本规格。

## 4. 阶段与职责

### 4.1 发射与提交

| 环节 | 契约 | 失败语义 |
|---|---|---|
| 写入口 | `Session.append(event_type, data)`:校验事件词表与 payload → 无损 JSON 快照 → 拒重入 → `log.push` | 非法事件/重入在发射点抛错(`SessionReentryError`);入日志即提交 |
| 通知 | 提交后同步触发已注册 `SessionObserver`;快照先于 push 解析,回调后于 push 执行 | observer 失败 contained 并记录,不使 append 失败 |
| 词表 | 闭集:`@session_event` 注册(`lca/contracts/harness/memory/events.py`)+ spine yaml 类别 | 未注册类型拒绝发射 |
| 派生 | `lca_kernel/events/fold.py` 纯函数从 `snapshot_events()` 重建 header / step tree | 无 I/O、无副作用 |

`session/event`(DSH)/ observer 通知是**提交后的通知**,不是「请求写入」:
事件已入日志才通知监听器;监听器失败不回滚已成功的 append。

代码锚点:`lca/plugins/session/runtime/session.py`(Session 实现)、
`lca_kernel/events/session.py`(SessionProtocol / SessionObserver / FlushListener)。

### 4.2 持久化(模块①,唯一写盘者)

| 环节 | 契约 | 失败语义 |
|---|---|---|
| 订阅拷贝 | `PersistenceObserver` 把已提交事件拷入 per-session 待写队列 | 不阻塞生产者;拷贝失败 = observer 失败,contained |
| write-behind | `WriteBehindBuffer`(`lca/infrastructure/persistence/`):首条待写事件开固定窗口(默认 200ms),后续事件不重置 deadline;到期批量写 `WriteBehindSink` | 背景写失败:事件保留、暂停自动重试、新事件开新窗口;`REQUIRED` 永不丢弃 |
| 显式排空 | `Session.flush()` → `FlushListener` 链,排空至静止 | 失败以 `FlushResult` 返回,由调用方决定阻断 |
| 工件 | 每 session 一个 JSONL;长驻句柄追加,每批一次 `flush` + 可选 `fsync`;`close()` 幂等 | 撕裂尾由读取端识别跳过;不静默截断已提交事件 |
| 元数据 | `SessionHeader` 与事件日志分离存放,不进事件词表 | 版本不匹配拒绝加载(不做隐式迁移) |

**append 解决 ≠ crash durable**:事件被接受、对当前后端实例可见,不等于
崩溃后仍存在;跨进程/崩溃后的持久性以显式 `flush()` 成功为界(durability
barrier)。后台写失败暂停自动路径并保留有序事件;下一次显式 flush 重试并把
错误报给调用者。dispose/close 执行最终排空,避免关闭丢事件。

恢复不变量:崩溃恢复不截断已提交事件;孤儿进行中的轮次以显式「中断」标记闭合,
而不是删除其事件。恢复只作用于冷 session;live session 的读取等待内存快照
落盘且平衡后返回。

### 4.3 消费三模块

#### 投影(模块②)

- 单元契约:`{key, init(header), apply(state, event), view?, state_version}`;
  `apply` 纯同步,对无关事件返回同一引用。
- 驱动:单一事件订阅把每个已提交事件急切穿过所有已注册单元;迟到注册从内存日志折历史。
- 出口:`snapshot()` 返回完整当前值 + 变更订阅;客户端收完整值,不收 fold 中间态。
- 缓存(如有):只是 fold 快捷方式,**永不是真值**;`state_version` 不匹配即弃行重折。

#### 标题(模块③)

- 标题是日志事件,不是旁路存储:标题服务生成结果经 `Session.append` 写回,
  事件 log-only,不进模型可见面。
- 确定性回退:首条合格用户消息,清洗(去控制字符、压缩空白)+ 长度上限;仅在无标题时追加。
- 可选 LLM provider:同一时刻至多一个;输出校验(非空、引用消息序列唯一有序);
  每 session 单调 revision,新修订取代在途旧工作;用户显式重命名钉住自动调度。
- 标题生成不阻塞主响应;失败静默保留回退。

#### 遥测(模块④)

- 后端三成员契约:`emit(record)`(必须非阻塞入队)/ `flush()`(可选)/ `shutdown()`(排空至静止)。
- 捕获协调器订阅已提交事件与错误,投影为遥测记录;每后端声明共享策略
  (full / feedback-only / disabled)供披露面展示;默认 disabled。
- 脱敏钩子在出站前执行;钩子抛错扣下该条记录(fail-closed);canonical 日志永不被改写。
- 后端错误全部 contained,不回灌日志。

## 5. 一次完整回合的时序

```text
用户输入 → inbox(claim)
  → turn.started                       [append → observer → write-behind]
  → step.started                       [append → observer → write-behind]
  → message.accepted(用户消息,surface) [append → 参与模型历史 fold]
  → (装配 system prompt + 工具 schema)
  → 模型请求边界                        [★ flush 检查点:请求前已提交事件必须先落盘]
  → model.requested → 瞬时流式帧(SSE,不落盘)→ model.completed
  → assistant.responded(surface)       [append → 参与模型历史 fold]
  → 工具调用(若有):
      Journal 平面记录工具事实(ToolStarted/ToolInvoked/ToolDenied,
      invocation_id 联结;Session 平面不重复承载工具词表——
      harness-spine-spec §2.2.3 明确禁止 tool.*.v1 session 事件)
      顶层副作用边界                    [★ flush 检查点:执行前落盘]
      需审批时:approval.persisted / approval.resolved
  → step.ended                         [append → observer → write-behind]
  → (若继续下一轮模型请求,回到模型请求边界)
  → turn.ended                         [append → observer → write-behind]
  → 显式 flush / 检查点策略排空
```

★ 处即 DSH `session-checkpoint-policy` 的三个 fail-closed 边界
(模型请求前、顶层工具副作用前、步边界);flush 失败则下游不执行。

与 DSH 的结构差异:DSH 把 `tool/call` / `tool/result` 作为 Session 事件;
LCA 的工具事实由 **Journal 平面**拥有(Session 平面承载审批与恢复锚点)。
两平面同源于 append 提交链,消费面按平面各取所需。

## 6. 落盘后的消费能力

| 能力 | 机制 | LCA 锚点 |
|---|---|---|
| 模型上下文重建 | surface fold:仅表面事件投影为消息历史;结算消息权威,瞬时/中间事件跳过 | `lca_kernel/events/fold.py`、`ModelVisibleFoldSource` |
| Resume | 打开存储日志 → 恢复到最后一个合法连续前缀 → 派生模型历史与运行状态 | `harness/session/recovery.py`、`resume_point.py` |
| Replay | 按 seq 重放已提交事件;瞬时流不作为独立事实 | `harness/session/replay.py`、`observability/replay/cursor.py` |
| 工具结果修复 | 有 call 无 result → 记「结果未知」,不盲目重试可能有副作用的工具 | 恢复语义(阶段 1 对照中) |
| Fork / Search | DSH:live-session fork(lineage + inherited cut)、session-query 检索 | LCA 暂无对应面(gap,不阻塞本规格) |
| UI 双轨 | 实时看瞬时流,最终确认以结算事件为准,刷新从持久日志重建 | `observability/sse/`、webserver trajectory handlers |

## 7. 插件化组织(挂载与激活)

四个模块全部走扩展路径:Protocol → Seam → Provider → Plugin → Bundle/Profile。

| 模块 | contracts 契约 | 出厂实现 | 挂载点 |
|---|---|---|---|
| 持久化 | `SessionPersistence` Protocol(`lca/contracts/protocols/session/session_persistence.py`)+ `WriteBehindSink` | `plugins/session/persistence_jsonl/` + `infrastructure/persistence/` | `bundles/session-runtime.yaml` |
| 投影 | 单元契约 + 注册表 | `harness/projection/` 各单元 | 投影 provider 插件 |
| 标题 | 标题服务 + 事件词 | 确定性回退(内置)+ 可选 LLM provider | Profile 可选挂载 |
| 遥测 | 三成员后端契约 | 复用 `observability/journal/otel/` 出站通道 | Profile 可选挂载 |

激活规则:能力可用性驱动——挂载持久化插件后,依赖 `session.store` /
flush 能力的插件才激活;未挂载持久化时循环照常运行,只是不产生持久工件。
禁止:模块间直接 import;绕过 `Session.append` 写日志;消费模块写盘。

## 8. 所有权与失败矩阵

| 模块 | 拥有 | 读 | 写 | 失败语义 |
|---|---|---|---|---|
| 持久化 | 每 session 持久工件 + header | 已提交事件 / flush 请求 | 磁盘工件(唯一授权) | 背景写失败保留+暂停;显式 flush 失败上报;恢复不截断 |
| 投影 | 派生当前值(可重建) | 已提交事件 | 无(缓存非真值) | 单元错误不波及;缓存失效即重折 |
| 标题 | 无(标题是事件) | 用户消息投影 | 仅经 `Session.append` | provider 失败保留回退;不阻塞响应 |
| 遥测 | 无 | 已提交事件 + 错误 | 仅出站队列 | 后端错误 contained;脱敏 fail-closed |

## 9. LCA 既有组件的融化归属(现状)

| 既有组件 | 归入 | 状态 |
|---|---|---|
| `lca/infrastructure/persistence/`(write-behind + JSONL sink) | 模块① | 已接线:`FilesystemJournalStore` 与 `plugins/session/persistence_jsonl` 共用 |
| `lca_kernel/events/persistence.py` `PersistenceObserver` | 模块① | 在用 |
| `plugins/session/persistence_jsonl/` | 模块① | 出厂后端,write-behind 形态 |
| `plugins/session/checkpoint_policy/` | 模块① | 已建成并挂载 `bundles/session-runtime.yaml`;循环边界接线(模型请求/工具副作用)属融合阶段 |
| `plugins/session/runtime/{recovery,resume_point}.py` | 模块①恢复段 | 自旧 `harness/session/` 迁入(approval 一致性 fold 与恢复点序列化) |
| `plugins/session/{projection_registry,projection_cache,session_stats,session_turn_outline}/` | 模块② | 已建成并挂载 |
| `harness/projection/agent_state.py` | 模块②例外保留 | C12 reducer fold 镜像,守护测试锁定;旧 `registry.py`/`web.py` 已退役(被新投影家族取代) |
| `plugins/session/{title_service,title_llm_provider}/` | 模块③ | 已建成;事件词 `session.title.v1` 注册于 `lca/contracts/harness/memory/events.py`(ADR-0188) |
| `plugins/session/{telemetry_capture,telemetry_otel}/` | 模块④ | 已建成并挂载;otel 默认 `DISABLED` |
| `harness/session/emit.py` | 发射面 | typed 事件对象 → `Session.append` 的统一发射出口 |
| `observability/journal/otel/` + GenAI 语义映射 + `telemetry_catalog.py` | 模块④出站 | Journal 平面投影保留;session 遥测出站通道复用属融合阶段 |

## 10. 迁移与退出(现状)

旧平面已退役删除(非兼容分支):`harness/session/{store,persistence,inbox,inbox_projection,replay,event_validation}.py`、
`harness/agent/`(AgentRegistry/SessionActivator/命令路由/审批恢复执行器全链)、
`harness/command/`、`application/{harness_live,harness_bridge,live_session_state,followup_dispatch}.py`、
`plugins/runtime/session_live_builder.py`、`plugins/loop_drivers/cognitive.py`、
collaboration 三个 session provider、webserver `/v1/sessions` 路由面。
验证:`rg "SessionStore|AgentRegistry|SessionActivator|JsonlSessionPersistenceFactory" lca/` 生产路径为 0。

仍在跟踪的迁移项(ADR-0186 §5 / DSH-GAP-AUDIT):

| 项 | delete-when(可观察条件) |
|---|---|
| EventSpine shim 直接 append(PR-3h) | `rg "event_spine.append\|spine_port_append" lca/` 仅存于 shim 自身 |
| `plugins/events/sinks/spine_file_sink` COMPAT | ADR-0186 PR-9 收口 |
| 事件信封唯一化后续 | kernel `SessionEvent` = contracts 信封(已统一);`SessionHeader` 以 kernel 版为唯一形态(已扩业务 lineage 字段) |

新代码默认走新平面;同一变更不得既新增旧用法又声称收敛迁移。

## 11. 排查清单(按链路顺序提问)

1. 它属于哪个平面——spine 总线(Journal)、Session 词表,还是仅 observer 通知?
2. 若是 Session 事件:谁调了 `Session.append`?校验是否通过?分到哪个 seq?
3. 哪些 observer 消费了它?有没有 observer 失败被 contained(查结构化日志)?
4. write-behind 缓冲收到了吗?窗口是否到期?(`pending_count` 诊断)
5. 是否经过显式 `flush()` 形成 durability barrier?`FlushResult.ok` 是什么?
6. 物理工件存在吗?尾部是否撕裂(读取端跳过了几行)?
7. 下游用的是 fold 派生、投影状态,还是违规直读原始日志/旧 sidecar?

操作入口:`./scripts/lca-ops debug-run <run_id>`、`journal trace`;
调试流程见 [docs/debug/README.md](../debug/README.md)。

## 12. 验证

| 断言 | 检查 |
|---|---|
| 唯一写入口 | 架构测试:`Session.append` 之外无日志写入(见 `tests/architecture/test_session_ssot_invariants.py`) |
| write-behind 语义 | `tests/infrastructure/test_write_behind.py`(窗口/失败保留/背压/排空/幂等关闭) |
| 恢复不截断 | 撕裂尾 + 孤儿轮次回归测试(模块①落地时补) |
| 词表闭集 | `@session_event` 注册集 ⟺ 消费方引用集一致 |
| 文档门禁 | `scripts/verify_md_links.py` + `scripts/verify_doc_budgets.py` + `scripts/check_doc_layering.py --strict` |

## 13. DSH 对照(参考坐标,非链接)

对照实现位于本机 `~/deepseek-harness`(非本仓库依赖,不作链接):

- `packages/core/session/src/index.ts` — Session append / observer / fold / `deriveMessages()`
- `packages/core/session/src/known-event-types.ts` — 词表(注意:**无** `assistant/attempt`;
  流式增量是 `assistant/chunk`,它随日志无损持久化(seq 连续性要求),派生时被跳过,
  结算 `assistant/message` 权威;失败尝试的用量记录留在 `llm/retry` + usage chunk)
- `packages/session/session-persistence{,-jsonl}` + `session-checkpoint-policy` — 模块①
  (格式版本不匹配拒绝加载,无隐式迁移链)
- `packages/session/session-projection{,-cache}` + `session-stats` / `session-turn-outline` — 模块②
- `packages/session/session-title{,-llm,-first-prompt-llm,-all-prompts-llm}` — 模块③
- `packages/session/session-telemetry{,-otel}` — 模块④
- `docs/subsystems/{session,persistence,session-projection,session-title,session-telemetry,tools}.md`
