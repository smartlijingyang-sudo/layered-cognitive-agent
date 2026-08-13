# Run Live —— 从第一性原理重建「人看 Agent 干活」

**状态**: Implemented（取代 ADR-0053 的实现形态；不推翻 ADR-0037 Journal-as-Truth）
**日期**: 2026-08-13
**修订**: 补设计模式 / SRP / 边界 / 稳定性 / 调用链 / 效率 / 原生改动面 / 前后端职责 / 业界范式 / 可观测诊断 / 自动校验
**前置**: 全链路评估（LobeHub → gateway → SSE → 前端）

> 给后续执行者：先读「第一性原理」「目标心智模型」「职责矩阵」，再动文件。
> 禁止在旧模块上继续长补丁。每个新文件必须能回答：「删掉它，哪个问题无法回答？」
> 每一条原则必须能落成测试或 lint，否则是口号。

---

## 1. 问题的本质（不是技术清单）

人在聊天框里打一句话。一个 Agent 在另一个进程里思考、调工具、写答案。人要**同时**看见这件事发生。

这件事只需要三个能力：

1. **开工** —— 把 UI 里的一条用户消息变成一次 Run
2. **记账** —— Run 过程中发生的事实只写一本账
3. **转播** —— 账本有两个读者：磁盘（给未来的自己）、套接字（给正在看的人）

人眼前的画面必须是 **LobeHub 自己的画面**：一块正在展开的 Thinking、一张原生工具卡、一段答案流。不是我们发明的第三种 UI。

当前系统失败在：为「转播」发明了第四、第五种语言。

```
Journal 事件
  → EventStream（平行总线）
    → TimelineEvent（第二套类型）
      → LobeHub SSE payload（第三套 dict）
        → Transport.applyEvent（第四套状态机）
          → dispatchMessage
```

四种形状说同一句话：「模型想了一段话」。排查要走四层。这不是架构，是考古现场。

---

## 2. 第一性原理

### 2.1 一本账，不是一条管道

ADR-0037 已经说完：**Journal 是唯一真相**。OTel、console、jsonl、SSE 都是投影。

仓库里其实已经有这个投影器族：

| 投影器 | 读者 |
|---|---|
| `JsonlJournalProjector` | 磁盘 |
| `OtelProjector` | Langfuse |
| `SSEJournalProjector` + `stamped_to_sse_frame` | 套接字（事件类名即 SSE `event:`） |

Gateway 没有用它们，另起了 `EventStream` + `TimelineProjection` + `LobeHubSSEAdapter` + `timeline.v1`。

**原则：禁止为同一种事实再发明一套类型系统。**

### 2.2 词表只允许两套

| 词表 | 谁用 | 例子 |
|---|---|---|
| Journal | 后端、jsonl、debug、SSE 线上事件名 | `ReasoningDelta` `ToolStarted` `ToolInvoked` |
| LobeHub 原生 | 前端渲染 | `StreamChunk.reasoning` `tool_calls` `ChatToolPayload` |

中间不许再出现：`thinking.delta`、`timeline.v1`、`lca.events`、`lca_tool_event`。

翻译发生 **恰好一次**，地点是 **UI 的门口**（Transport），因为：

- LobeHub 类型随上游升级而变，翻译必须和前端补丁住在一起
- Journal 形状是 LCA 的契约，不随 UI 变
- 同一条 SSE 人和 `curl` 都能读：`event: ToolStarted` 和 jsonl 里的 `"event_type": "ToolStarted"` 是同一个词

### 2.3 状态只造一次

工具卡片的 `plugin_state` 在 `SafeExecutor` 出厂时就已经是 LobeHub 形（`tool_ui_state`）。

**原则：账本里有的结构，禁止在投影层再拼一遍。**

Adapter 里 15 个 `build_*_state`、Projection 里的 seed `tool.delta`、Transport 里的第三次 merge —— 全部删除。

### 2.4 前端禁止私造渲染管道

LobeHub 已经有：

- `StreamingHandler`：reasoning operation、文本累积、tool_calls 节流、动画
- `Thinking`：一块手风琴，靠 `isMessageInReasoning` 自动展开/收起
- 内置工具 Render：`executeCode` / `runCommand` / `search` / `activateSkill`

**原则：Transport 只做两件事——拉流、把 Journal 事件喂给 StreamingHandler。**

不允许再写 `applyEvent` + 全量 `dispatchMessage`。

### 2.5 深度思考：跟原生，不发明多段

原生一次 `call_llm` = 一个 `StreamingHandler` = **一块** Thinking。工具跑完，下一轮 LLM 覆盖这一块。用户看见的是「当前这次在想什么」。

「把每一轮思考都堆进同一个 multimodal `tempDisplayContent`」既不是原生，也不是「每次一个」。那是用错误通道模拟时间线。

本重构 **明确不做** 多段 Thinking 手风琴。若产品以后要「步骤轨」，那是新 UI，不是 Reasoning 组件的旁路。

本重构要做到的原生行为：

- `ReasoningDelta` 到来 → `startOperation('reasoning')` → 手风琴展开、字往外蹦
- `ToolStarted` 或答案文本到来 → reasoning 结束 → 手风琴按原生逻辑收起
- 下一轮思考重新展开，**内容替换为本轮**（不拼接历史）

### 2.6 每个文件必须通过「删除测试」

删掉这个文件之后，下面三个问题至少有一个无法回答，才允许它存在：

1. 这次 Run 怎么开工的？
2. 事实写到哪、谁在读？
3. 人眼前的原生组件怎么被驱动的？

通不过的，是历史，不是架构。

### 2.7 定制只为闭环

LobeHub 默认假设：**模型提出 tool_calls → 浏览器执行 → 结果回去再问模型**。

LCA 是：**工具在服务端沙箱里跑完**。所以必须有且仅有一处告诉运行时「不要再开客户端 tool loop」——`lcaClosedLoop`。

除此之外，每一处对 LobeHub 源码的改动都必须能写成一句：「因为上游缺 X，而 X 无法在不改上游的情况下用契约表达。」

---

## 3. 目标心智模型（人与 Agent 共用）

任何人（或 Agent）打开这条链路，只需要记住这一段：

```
一次用户消息 = 一次 Run。
一次 Run 有一本 Journal。
Journal 有两个读者：jsonl 文件、LiveTail。
浏览器订 LiveTail，事件名 = Python 类名 = jsonl 的 event_type。
前端 JournalTransport 把事件喂给 LobeHub 自己的 StreamingHandler。
工具卡用 Journal 里已经写好的 plugin_state。
```

排查四步，不能再多：

```
1. jsonl 里有没有这条事件？     → 没写：查 SafeExecutor / LLM adapter
2. LiveTail 有没有送出去？       → 查 /runs/{id}/live + Last-Event-ID
3. Transport 有没有喂对 chunk？  → 查 JournalTransport 的一张映射表
4. StreamingHandler / 卡片渲染   → 那是 LobeHub 的事，不是我们的
```

对比现在的六步（还含一个静默丢事件的盲区）：这就是重构要买到的东西。

---

## 4. 目标拓扑

```
Browser
  └─ AgentRuntime
       └─ JournalTransport          ← 唯一 LCA 补丁入口（llm transport）
            │ POST /runs            { messages, model }
            │ GET  /runs/{id}/live  text/event-stream  (Last-Event-ID)
            ▼
Starlette (gateway/app.py)          ← 只注册路由，无业务
  ├─ POST /runs                     runs/api.py
  ├─ GET  /runs/{id}/live
  ├─ GET  /runs/{id}
  ├─ POST /runs/{id}/cancel
  ├─ POST /runs/{id}/answer
  ├─ GET  /files/{id}               files.py
  └─ /v1/chat|embeddings|responses  openai_shim.py   ← 系统小助手，不是 Agent
            │
            ▼
RunSession                          ← 一个对象 = 一次 Run
  hub: ObservabilityHub             只经 create_observability() 装配
    读者: jsonl / LiveTail / Langfuse（有凭据则挂）
  agent | team                      干活的人
            │
            ▼
record(ReasoningDelta | ToolStarted | …)
  → 每个 projector.on_event
```

没有：`EventStream`、`TimelineEvent`、`timeline.v1`、`LobeHubSSEAdapter`、`compose_sse_stream` 管道、`_active_hubs`、`_jsonl_consumer`、`applyEvent`。

---

## 5. 目标文件树（每一份的存在理由）

### 5.1 gateway —— 允许存在的文件

```
gateway/
  __init__.py              导出 app / create_app
  app.py                   组合根：路由表 + 注入点。禁止业务分支
  cors.py                  CORS 头 SSOT（现 _http.py 改名）
  modes.py                 solo/team 元数据 + model id 映射
  assemble.py              build_solo_agent / build_runnable_team
  openai_shim.py           title / embeddings / responses / structured
  files.py                 GET /files/{id} 与 meta
  runs/
    __init__.py
    api.py                 Run 的 HTTP：create / live / get / cancel / answer
    session.py             RunSession + RunRegistry + inflight 指纹
    execute.py             scope 装配、跑 Agent/Team、统一 teardown
    ingress.py             LobeHub messages[] → RunInput
    ingest.py              附件：SSRF、下载、缓存、data URI
    live.py                LiveTail(JournalProjector) —— 订阅/回放/心跳
    doctor.py              diagnose()：读 jsonl+session → doctor.v1（无 HTTP、无翻译）
    wire.py                LCA 工具名 → (identifier, apiName) 一张表
```

**17 个文件**（含 `doctor.py`：新读者，通过删除测试——删了它就无法自动回答「断在哪一跳」）。现在 gateway 源文件约 35+。删除测试见 §5.3。

`wire.py` 为什么还在 Python 而不只在前端？因为测试和未来第二个消费者（CLI）需要同一张坐标表。它 **只许** 是 `dict[str, tuple[str, str]]` + 一个 `resolve(name) -> Wire`。禁止 `build_state` / `adapt_args`。参数以 `plugin_state` 为准。

`ingest.py` 为什么独立？附件镜像是完整子系统（SSRF + 缓存 + 体积上限），和「解析 messages」不是一件事。

`openai_shim.py` 为什么还在？LobeHub 的标题生成 / AgentSignal `generateObject` 仍走 OpenAI 形 API。这是 **另一个问题**，禁止再和 Run 合流。

### 5.2 前端补丁 —— 允许存在的

| 补丁 | 存在理由 |
|---|---|
| `journal_transport` | 唯一生产入口：订 Journal live，喂 StreamingHandler |
| `call_llm_finalizer` | 上游没有「服务端已跑完工具」这个开关 |
| `file_proxy_rewrite` | 浏览器要拿产物；Next rewrite `/files`、`/lca-api` |
| `sandbox_generated_files` | 上游 ExecuteCode 卡片不渲染 `state.files` |
| `default_model` | 默认模型必须是 `solo` |
| `openai_guard` | 标题等小请求仍走 model-runtime，防止 `solo` 进 Responses API |
| `dev_auth_*` / `lan_dev` / `topic_route` | 开发体验 / 路由，与 Run 协议无关，保持原状 |

**删除整个 `patches/streaming/`**（空壳，旧 `lca.events` 时代）。
**删除** `agent_timeline_transport.py`（被 `journal_transport` 替换）。

### 5.3 删除清单（源码，不是改名）

| 删除 | 理由 |
|---|---|
| `gateway/event_stream.py` | LiveTail 就是它，且必须是 JournalProjector，不能是平行总线 |
| `gateway/timeline/` 整包 | 第三套词表。`types.py` `projection.py` `lobehub_adapter.py` `sse_encode.py` `stream.py` `error_sanitizer.py` |
| `gateway/lobehub_bridge/` 整包 | 拆进 `ingress.py` + `ingest.py` + `wire.py` |
| `gateway/lobehub_bridge/lobehub_adapter/tool_registry.py` 的 state builders | 状态已在 Journal |
| `run_executor._jsonl_consumer` / aiofiles 路径 | 用已有 `JsonlJournalProjector` |
| `run_executor._active_hubs` | Hub 挂在 RunSession 上 |
| `run_executor._EventStreamProjector` | LiveTail 自己就是 projector |
| `patches/runtime/agent_timeline_transport.py` | 旁路渲染器 |
| `patches/streaming/` | 无源码，旧协议 |
| 所有对应 pycache / 过时文档段落 | 假地图 |

layer0 的 `sse_frames.py` / `SSEJournalProjector` **保留并成为线上契约**。gateway 不再复制一套 encode。

### 5.4 明确不改

- `lca/layer1_cognitive/body/tool_ui_state.py` 及 builders —— 状态 SSOT
- `lca/layer0_infra/observability/journal/` 事件类型与 catalog
- Agent / Team 运行时、casting、sandbox
- `/v1/chat/completions` 对 title 的 hard cut（保持：agent 走 `/runs`）

---

## 6. 协议（线上唯一）

### 6.1 HTTP

| 方法 | 路径 | 作用 |
|---|---|---|
| `POST` | `/runs` | 开工。body: `{ messages, model }`。202 + `{ run_id, trace_id, live_url }` |
| `GET` | `/runs/{id}/live` | Journal SSE。认 `Last-Event-ID` |
| `GET` | `/runs/{id}` | 快照：status / error / mode |
| `GET` | `/runs/{id}/doctor` | `doctor.v1` 探针裁决。纯查询，不推动 Run |
| `POST` | `/runs/{id}/cancel` | 取消。Transport abort 时 **必须** 打这个 |
| `POST` | `/runs/{id}/answer` | HIL。本轮只保证事件能出现在 live 上；UI 表单可后置 |
| `GET` | `/files/{id}` | 产物 |

删除：`POST /v1/agent/runs`、`GET /v1/agent/runs/{id}/timeline`。
Next rewrite：`/lca-api/:path*` → gateway 根路径（不再先加 `/v1` 再剥）。

### 6.2 SSE 帧 = Journal 帧

已有实现，禁止改形状：

```
id: {seq}
event: {JournalEvent 类名}
data: { stamped_to_record(stamped) + domain }

: keepalive          ← 空闲 15s，注释帧，防代理掐线
```

`curl -N localhost:8765/runs/$ID/live` 的输出必须能和 `traces/runs/$ID.jsonl` 对上号。

心跳不是事件，没有 `id`，不进 Last-Event-ID。

Buffer 被环形淘汰时：先发一帧

```
event: LiveGap
data: {"requested_seq": N, "oldest_seq": M}
```

`LiveGap` 是 **传输控制信号**，不是 Journal 事件。这是 LiveTail 唯一允许发明的事件名。前端收到后：用 `oldest_seq-1` 重订，或接受缺口（v1 接受缺口并打日志；不在本轮做 jsonl HTTP 回放）。

### 6.3 前端映射表（JournalTransport 里唯一的 switch）

| SSE `event` | 喂给 StreamingHandler | 备注 |
|---|---|---|
| `ReasoningDelta` | `{ type: 'reasoning', text }` | 触发 `onReasoningStart` |
| `ReasoningCompleted` | 忽略（下一则 text/tool 会 `endReasoningIfNeeded`） | 不拼多段 |
| `StepTextDelta` 且 channel=answer | `{ type: 'text', text }` | decision channel 后端可不发；前端也丢 |
| `ToolStarted` | `{ type: 'tool_calls', tool_calls, isAnimationActives }` | `function.name` = `identifier____apiName`；arguments 从 plugin_state 抽 |
| `SandboxOutputDelta` | `onToolCallsUpdate` 补 `result.state.stdout/stderr` | 不新增 chunk 类型 |
| `ToolInvoked` | 更新 `result` + 对应位动画 `false` | `plugin_state` 原样进 `result.state` |
| `ToolDenied` | 更新该工具 `result.error`；无卡片则忽略 | **禁止**写进答案正文 |
| `AgentRunFinished` / `TeamRunFinished` | `{ type: 'stop' }` + `lcaClosedLoop: true` | error 走 handler 失败路径 |
| `LiveGap` | 打日志；不中断 | |
| 其它（Casting*、Delegation*、LlmCall*、RunInsight…） | **忽略** | 它们属于 jsonl / Langfuse，不属于聊天泡泡 |

Delegation 不再变成 `↣ **委派**` Markdown。团队叙事在 Journal / Langfuse，不污染助手正文。

### 6.4 工具坐标（`wire.py` 全文量级）

```python
# 唯一允许的表。新增工具：一行。禁止函数。
WIRE: dict[str, tuple[str, str]] = {
    "execute_code": ("lobe-cloud-sandbox", "executeCode"),
    "run_command": ("lobe-cloud-sandbox", "runCommand"),
    "list_files": ("lobe-cloud-sandbox", "listFiles"),
    "read_file": ("lobe-cloud-sandbox", "readFile"),
    "write_file": ("lobe-cloud-sandbox", "writeFile"),
    "edit_file": ("lobe-cloud-sandbox", "editFile"),
    "search_files": ("lobe-cloud-sandbox", "searchFiles"),
    "move_files": ("lobe-cloud-sandbox", "moveFiles"),
    "grep_content": ("lobe-cloud-sandbox", "grepContent"),
    "glob_files": ("lobe-cloud-sandbox", "globFiles"),
    "get_command_output": ("lobe-cloud-sandbox", "getCommandOutput"),
    "kill_command": ("lobe-cloud-sandbox", "killCommand"),
    "export_file": ("lobe-cloud-sandbox", "exportFile"),
    "activate_skill": ("lobe-skills", "activateSkill"),
    "run_skill_script": ("lobe-skills", "execScript"),
    "read_skill_reference": ("lobe-skills", "readReference"),
    "search_skill": ("lobe-skill-store", "searchSkill"),
    "import_skill": ("lobe-skill-store", "importSkill"),
    "web_search": ("lobe-web-browsing", "search"),
    "ask_user_question": ("lobe-user-interaction", "askUserQuestion"),
    "write_file_local": ("lobe-local-system", "writeFile"),
}
```

前端内嵌同一张表（生成或手抄，必须有单测断言两边相等）。`function.name` = `identifier + "____" + apiName`，LobeHub `transformToolCalls` 原样吃。

`import_skill` 的 market / zip 分叉：用 `plugin_state` 或 args 里是否有 `identifier` 在 Transport 里选 `importFromMarket` vs `importSkill`。不要为此回到 factory 函数注册表。

### 6.5 本轮思考替换，不拼接

Transport 持有 `turnHadTool = false`。

- `ToolStarted` / `ToolInvoked` → `turnHadTool = true`
- 下一条 `ReasoningDelta` 且 `turnHadTool` → **新的 StreamingHandler**（或重置 handler 的 thinking 缓冲，若我们愿意给 StreamingHandler 加一个 3 行的 `resetReasoning()` 补丁——**不建议**，新建 handler 更零侵入）
- 旧 handler `handleFinish` 一次，新 handler 接管后续 chunk
- 消息上的 `reasoning` 被新一轮覆盖 = 原生多轮 `call_llm` 行为

---

## 7. 关键对象的职责（不许膨胀）

### 7.1 `LiveTail`（`runs/live.py`）

它是 `JournalProjector`。不是总线，不是协议，不是过滤器。

职责：

- `on_event`：写入环形缓冲，投递给订阅者队列
- `subscribe(after_seq)`：先注册再回放再 live（无竞态）
- 连续溢出 N 次踢掉死订阅者（打日志，不许静默）
- `close`：sentinel
- 空闲由 HTTP 层发 SSE 注释心跳（LiveTail 不懂 HTTP）

过滤器（RunInsight、decision channel）**不要**放进来。jsonl 要完整事件。过滤发生在 Transport 的映射表（忽略即过滤）。若带宽成为问题，再在 `subscribe` 加可选 mask——本轮不做。

现有 `EventStream` 的算法（deque 4096、queue 256、溢出阈值 3、GapEvent）原样搬进 LiveTail，换一个诚实的名字和接口。

layer0 的 `SSEJournalProjector`（`emit` 回调、无回放）**不与 LiveTail 并用**。Gateway 的读者是 LiveTail；`stamped_to_sse_frame` 只在 HTTP 层调用。`SSEJournalProjector` 可留作 layer0 单测/其它入口，但 `execute` 不得再挂一个。两个 live 投影器 = 双写。

### 7.2 `RunSession`

字段：`run_id, trace_id, jsonl_path, hub, tail, question, user_text, mode, prior_turns, attachment_ids, status, error, task, cancel_requested, snapshot, runnable, approval_request`。

Hub 在 session 上。Resume 从 `session.hub` 取。没有模块级 dict。

### 7.3 `execute.py`

```
create_session:
  tail = LiveTail()
  hub = ObservabilityHub(journal_projectors=[
      JsonlJournalProjector(jsonl_path),
      tail,
  ])
  session = RunSession(hub=hub, tail=tail, ...)
  registry.put(session)

execute:
  bind run_id / attachments / workspace / sandbox / search
  run agent|team
  HIL → status=WAITING_INPUT, return（不 close tail）
  else → finalize

finalize（唯一 teardown，嵌套 finally）:
  artifact closure 若需要
  finalize_run(workspace)
  hub.close()          # 关 journal + 投影器（tail.close 在 projector.close）
  写 status
  清 inflight
```

禁止 `execute` 和 `_resume_run` 各写一份 finally。

### 7.4 `ingress.py`

输入：OpenAI 形 `messages[]`。
输出：`RunInput(user_text, question, prior_turns, attachment_ids, skipped)`。

内部步骤按函数排，不要再拆文件，除非单文件超过 400 行有效代码：

1. 抽最后一轮可见用户文本（剥 SYSTEM CONTEXT / available_tools / eval envelope）
2. 抽 `<file>` / `image_url`
3. 有界历史
4. 调 `ingest.py`
5. 拼附件说明 + 用户问题

### 7.5 `JournalTransport`（前端）

结构对标 `ClientLLMTransport`，只换数据源：

```
runAttempt:
  POST /lca-api/runs
  GET  /lca-api/runs/{id}/live   + Last-Event-ID + abort → POST cancel
  const handler = new StreamingHandler(ctx, callbacks)  // 与 ClientLLMTransport 同一套 callbacks
  for await (frame of readSse(res)) {
    dispatch(handler, frame)   // 只有 §6.3 那张表
  }
  return { ..., lcaClosedLoop: true, toolsCalling: handler.getTools() }
```

`readSse` 可以 40 行内写完；不要引入 fetchSSE 再补 `lca_tool_event` 类型——那是旧协议。

节流：交给 StreamingHandler 已有的 300ms tool throttle。reasoning 的 `onReasoningUpdate` 是原生路径，不再每次附带整包 tools。

---

## 8. 错误、取消、重连、HIL

| 场景 | 行为 |
|---|---|
| LLM 没配 | `POST /runs` → 503，和现在一样 |
| 跑崩 | Journal 记 `AgentRunFinished(error=…)`；脱敏留在 **记录点** 或一层纯函数，不单独搞 SanitizerChain 包 |
| 用户点停止 | abort fetch **并且** `POST /runs/{id}/cancel` |
| 断线 | 浏览器用最后一帧 `id` 重开 `/live`；LiveTail 回放 |
| LiveGap | 日志 + 继续；不承诺补齐被淘汰的思考 delta |
| HIL | status=`waiting_input` 出现在 `GET /runs/{id}`；live 上会停在最后一条业务事件且 **不 close**。UI 表单本轮不做，但事件不得把 tail 关掉 |

错误脱敏：3 条正则，放 `execute.py` 或 `api.py` 一个函数。删除 `error_sanitizer.py` 的 Protocol 剧院。

---

## 9. 文档与认知卫生

重构落地时必须同步改，否则下一轮按假地图施工：

| 文档 | 改成 |
|---|---|
| `deploy/lobehub/CUSTOMIZATIONS.md` | 只列 §5.2 那张最小补丁表。删掉整节「lca.events / openai_stream」 |
| `docs/lobehub-integration.md` | 图画 `POST /runs` + `GET /runs/{id}/live` |
| `docs/agent-timeline.md` | **删除或改名为 `docs/run-live.md`**，声明 timeline.v1 已废 |
| `docs/adr-0053-gateway-sse-architecture.md` | 文首加 Superseded by 本 spec；保留作历史 |
| 本 spec | 作为新的 SSOT |

---

## 10. 测试策略（先测契约，再拆旧代码）

新契约测试（先写，旧实现先适配让它们绿，再拆）：

1. `stamped_to_sse_frame`：`event:` == 类名，`id:` == seq，与 jsonl record 同构（已有，保持）
2. `POST /runs` 202 后 `GET /live` 能读到 `AgentRunStarted` / `ReasoningDelta` / `ToolStarted` / `ToolInvoked` / `AgentRunFinished`
3. `Last-Event-ID` 回放不丢、不重复
4. `wire.py` 与前端表一一对应
5. `ToolStarted.plugin_state` 原样出现在 SSE data 里，**没有**被 gateway 改写
6. 前端映射：`ReasoningDelta` → handler 收到 `type:'reasoning'`（可用纯函数单测，不跑浏览器）
7. `lcaClosedLoop` 仍让 `hasToolsCalling` 为 false
8. abort 触发 cancel API（gateway 单测 + Transport 单测）

旧测试迁移：

- `test_timeline_projector.py` → 删或改成「LiveTail 不翻译」
- `test_lobehub_tool_wire.py` → 缩成 wire 表
- `test_openai_compat_gateway.py` 的 agent 路径保持 400
- 表征测试若锁了 `thinking.delta` 字符串：改锁 `ReasoningDelta`

验证流水线（改完必跑，顺序不乱）：

```
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca gateway
uv run pytest
uv run vulture lca gateway --min-confidence 80
python3 deploy/lobehub/patch_lobehub.py verify
```

---

## 11. 分 PR / 切片（可独立合并，每刀可回滚）

原则：每一刀结束时，**用户仍能发一条消息并看到思考和工具卡**。允许中间态「线上仍是 timeline.v1，但 Journal 已双写」。不允许中间态「前端已切 Journal、后端还只发 thinking.delta」。

### PR1 —— 恢复 Journal 双读者（后端无协议变化）

- `LiveTail` 替换 `EventStream`，实现 `JournalProjector`
- `JsonlJournalProjector` 回到 Hub，删除 `_jsonl_consumer`
- Hub 挂到 `RunSession`，删除 `_active_hubs`
- `/timeline` 仍从 `session.tail.subscribe` 读，**暂时**仍跑旧 Projection→Adapter（包一层适配，不改帧）
- 验收：现有 pytest 全绿，前端零改动

### PR2 —— 线上改发 Journal 帧；旧 Adapter 删除

- `GET /runs/{id}/live` 输出 `stamped_to_sse_frame`
- 保留 `/v1/agent/runs/{id}/timeline` 一周，标 deprecated，内部转调 `/live`（或 301 语义的 JSON 提示）
- 删除 `gateway/timeline/`、`event_stream.py`、`lobehub_bridge/lobehub_adapter` 除 wire 表外的一切
- `lobehub_bridge` 搬迁为 `ingress.py` / `ingest.py` / `wire.py`
- 前端 **同一 PR** 换成 `JournalTransport`（否则会断）
- 验收：手测思考展开、executeCode 卡、产物链接、停止按钮打到 cancel

### PR3 —— HTTP 面削皮

- `POST /runs` 取代 `POST /v1/agent/runs`
- rewrite 不再经 `/v1`
- 删除 deprecated 路径
- 文档三件套重写
- 清 pycache 与空 `patches/streaming/`

### PR4（可选，独立）—— HIL UI

只在 PR2 的 live 已保证 HIL 不关 tail 之后做。本架构不阻塞。

---

## 12. 风险与非目标

**风险**

| 风险 | 缓解 |
|---|---|
| Journal 事件比 timeline 密（LlmCall* 等），打满前端 | Transport 忽略表；不在 LiveTail 过滤，避免 jsonl/live 不一致 |
| `plugin_state` 个别工具仍缺字段 | 修 `tool_ui_state`（出厂处），禁止在 gateway 补 |
| StreamingHandler 一轮思考覆盖上一轮 | 这是选定的原生语义，不是 bug |
| Next rewrite 改根路径漏改 | PR3 单独做，PR2 仍走 `/lca-api/agent/runs/...` 映射到新 live |
| `transformToolCalls` 不认我们的 wire 名 | 单测锁表；手测每张内置卡 |

**非目标（明确不做）**

- 多段 Thinking 手风琴
- 自研聊天 UI / 换掉 LobeHub
- 把 Journal 事件改成 OpenAI `chat.completion.chunk`
- WebSocket、Kafka、跨进程 EventBus
- 在 gateway 重建一套 LobeHub plugin 类型
- 把 title 生成并进 Run

---

## 16. 设计模式：只用有存在理由的，禁止剧院

本重构 **承认** 的模式（每种对应一个真实变化轴）：

| 模式 | 落点 | 变化轴（为什么不是过度设计） |
|---|---|---|
| **Projector** | `JsonlJournalProjector` / `LiveTail` / `OtelProjector` | 同一本账，读者会增减。新增读者 = 新投影器，不改 `record()` |
| **Composition Root** | `gateway/app.py` | 进程启动时装配。路由注册，禁止业务 `if` |
| **Session Aggregate** | `RunSession` | 一次 Run 的一致性边界：hub、tail、status、task 同生共死 |
| **Adapter at the edge** | `JournalTransport` | LobeHub 类型随上游变。翻译贴着消费者，不渗进 Journal |
| **Data table, not Strategy objects** | `wire.py` | 坐标是静态双射。一行数据，不是 15 个 `build_*` 策略类 |
| **Template teardown** | `execute.finalize` | 成功/失败/取消/HIL 共用一个结束顺序。禁止两份 `finally` |
| **Ignore as filter** | Transport 默认忽略未知 `event` | 前向兼容。新 Journal 事件不应炸前端 |

本重构 **拒绝** 的模式（当前代码里已经出现过，禁止回归）：

| 拒绝 | 为什么是剧院 |
|---|---|
| Gateway 里再做一套 Strategy Registry 拼 `plugin_state` | 出厂处已经有。第二套必分叉 |
| `ErrorSanitizer` Protocol + Chain of Responsibility | 3 条正则配不起一套类型体系 |
| EventBus / EventStream 作为 Journal 的上游 | 把真相降级成「总线的一种输入」 |
| TimelineEvent 联合类型作为「领域中立层」 | 消费者只有 LobeHub。中立层没有第二个实现，是假想的扩展点 |
| 前端 `applyEvent` 私造状态机 | 复制 `StreamingHandler`，少了 operation 生命周期 |
| 为过滤单独做一层 Projector | 忽略即过滤；过滤放 LiveTail 会让 jsonl 与 live 不一致 |

判断口诀：**变化轴不存在，就不引入间接层。** 「以后可能换前端」不是变化轴——真换的时候再写第二个 Transport，gateway 一行不改。

---

## 17. SRP：每个文件只有一个变化理由

「一个文件一件事」太空。用 **变化理由** 锁死：

| 文件 | 唯一允许的变化理由 | 禁止写进这个文件的东西 |
|---|---|---|
| `app.py` | 新增/删除 HTTP 路由或注入点 | 任何 `if model`、任何 Journal 类型 |
| `cors.py` | CORS 头策略变了 | 业务 |
| `modes.py` | 产品增加协作模式文案/映射 | 组队算法、HTTP |
| `assemble.py` | solo/team **怎么造** 变了 | HTTP、SSE、LobeHub 消息格式 |
| `openai_shim.py` | LobeHub 系统小助手 API 变了 | Agent Run、Journal |
| `files.py` | 下载/预览头变了 | Run 生命周期 |
| `runs/api.py` | Run 的 HTTP 契约变了 | Agent 内部、投影算法 |
| `runs/session.py` | Run 索引/去重/状态枚举变了 | 执行、解析 messages |
| `runs/execute.py` | 一次 Run 的 scope/teardown 变了 | Starlette `Request`、SSE 编码 |
| `runs/ingress.py` | LobeHub `messages[]` 形状变了 | 工具卡片、SSE |
| `runs/ingest.py` | 附件安全/缓存策略变了 | Agent、Journal 事件 |
| `runs/live.py` | 订阅/回放/背压算法变了 | HTTP、LobeHub、过滤表 |
| `runs/doctor.py` | 探针谓词变了 | HTTP 组装、事件翻译、改 session |
| `runs/wire.py` | 新增/改名一个内置工具坐标 | 任何函数、任何 state |
| `tool_ui_state.py`（layer1） | 某张原生卡片缺字段 | HTTP、SSE、wire 名 |
| `JournalTransport` | Journal 事件 ↔ StreamChunk 映射变了 | 拼 plugin_state、全量 setState |
| `call_llm_finalizer` 补丁 | 上游仍没有闭环开关 | 任何其它逻辑 |
| `file_proxy_rewrite` | 浏览器到 gateway 的入口路径变了 | 业务 |

**同层协作只通过参数，不通过模块级可变全局。** `_active_hubs` 这类 dict 是 SRP 破裂的气味：session 的一部分跑到了模块上。

### 17.1 允许的依赖（谁可以 import 谁）

```
app.py
  → cors, files, openai_shim, runs.api, assemble(仅测试注入)

runs.api
  → session, execute, ingress, live, cors
  ✗ assemble 的实现细节、✗ tool_ui_state、✗ journal 事件类（除类型标注）

runs.execute
  → session, assemble, live, layer0 hub/jsonl/scopes, layer4 Agent/Team
  ✗ starlette、✗ ingress 解析细节、✗ wire.py

runs.ingress
  → ingest, modes(不必须)
  ✗ live、✗ execute、✗ journal

runs.live
  → JournalProjector, StampedEvent
  ✗ starlette、✗ wire、✗ ingest、✗ assemble

runs.wire
  → 无内部依赖
  ✗ 任何其它 gateway 模块

JournalTransport
  → StreamingHandler, ChatStore operations, wire 表
  ✗ 自造消息渲染、✗ 直写 DOM
```

这条依赖图应能写成 `tests/test_run_import_boundaries.py`（AST 或 import linter 白名单）。比口号硬。

---

## 18. 边界：每个对象「知道什么 / 不知道什么」

| 对象 | 知道 | 不知道 |
|---|---|---|
| Journal | 事件类型、seq、scope | HTTP、LobeHub、工具卡 |
| LiveTail | `StampedEvent`、队列、seq | 事件语义、哪条该给前端 |
| Jsonl 投影器 | 如何把 stamped 写成一行 | 谁在读、SSE |
| `execute` | 如何把一次任务跑完并关干净 | 浏览器、chunk 类型 |
| `ingress` | LobeHub 怎样把文件塞进 messages | 工具怎么画 |
| `wire.py` | 内部名 ↔ 插件坐标 | 参数形状、执行结果 |
| `runs/api` | HTTP 动词与状态码 | `plugin_state` 字段 |
| JournalTransport | 事件名 → `StreamChunk` / handler 方法 | 沙箱、casting、委派 |
| StreamingHandler | 原生 reasoning/tool 生命周期 | Journal、LCA |
| `tool_ui_state` | 某工具的卡片字段 | 谁在投影 |

**边界违反的典型气味（出现即回滚）：**

1. `LiveTail.on_event` 里出现 `isinstance(..., RunInsight)`
2. `execute.py` 里出现 `encode_sse` / `text/event-stream`
3. `wire.py` 里出现 `def build_`
4. Transport 里出现 `plugin_state.stdout = buf + text` 的累积器（那是出厂 state + `SandboxOutputDelta` 的事）
5. gateway 里出现 `thinking.delta` 字符串
6. layer1 里出现 `identifier____apiName`（坐标属于 wire，不属于认知层）

第 6 条要钉死：`tool_ui_state` 出的是 **卡片字段**（`code`/`stdout`/`executionEnv`）。`____` 拼接只允许发生在 Transport（或 `wire.resolve` 的纯函数）。认知层不依赖 LobeHub 插件协议分隔符。

---

## 19. 前后端职责（合同，不是感觉）

把 SSE 帧当成 **唯一合同**。合同两侧各自的所有物：

### 19.1 后端必须保证

| 保证 | 不保证 |
|---|---|
| 每个 `record()` 的事件，jsonl 与 live **同序同形**（同一 `stamped_to_record`） | 前端画不画得出来 |
| `plugin_state` 在 `ToolStarted`/`ToolInvoked` 上完整、未被 gateway 改写 | `plugin_state` 让某张卡好看——那是 layer1 的保证 |
| `Last-Event-ID` 回放不丢不重（缓冲范围内） | 缓冲淘汰前的思考 delta 永远能补（有 `LiveGap`） |
| cancel 能打断 `session.task` | 浏览器是否记得打 cancel |
| HIL 时 **不** `hub.close()` | HIL 表单长什么样 |
| 附件以 `/files/{id}` **相对路径** 出现在 `files` 里 | 跨域绝对 URL（浏览器同源 + Next rewrite 即可） |

相对路径是刻意的：`absolutize_file_parts` + `LCA_GATEWAY_PUBLIC_URL` 是旧 Adapter 的认知负担。卡片里的 `href=/files/xxx` 走 Next rewrite，少一个环境变量，少一种「内网 127.0.0.1 链到浏览器」的 bug。

### 19.2 前端必须保证

| 保证 | 不保证 |
|---|---|
| 映射表覆盖 §6.3；未知事件忽略（不抛） | 解释 Casting/Delegation |
| `ReasoningDelta` 走 `onReasoningStart`，Thinking 能展开 | 多段手风琴 |
| `ToolStarted` 的 `function.name` 能被 `transformToolCalls` 吃进原生卡 | 重写 ExecuteCode Render |
| abort 时 **同时** abort fetch 与 `POST /runs/{id}/cancel` | 后端取消的实现 |
| `lcaClosedLoop: true` | 客户端再跑一遍工具 |
| 本轮思考覆盖，不拼接 | 步骤轨 |

### 19.3 变更该找谁（维护路由）

| 现象 | 第一责任 | 禁止去的地方 |
|---|---|---|
| jsonl 没有 `ToolStarted` | SafeExecutor / 工具执行 | Transport、Adapter（已删） |
| jsonl 有，curl live 没有 | LiveTail / finalize 过早 close | 前端 |
| live 有，卡片不出现 | Transport 映射 / wire 表 / `transformToolCalls` | gateway 再拼 state |
| 卡片出现但缺 `code`/`stdout` | `tool_ui_state` builders | `wire.py`、Transport 累积器 |
| 思考不展开 | Transport 没接 `onReasoningStart` | Reasoning.tsx 补丁 |
| 停止后 Agent 还在跑 | Transport 没打 cancel | 在前端「假装结束」 |
| 标题生成失败 | `openai_shim` / `openai_guard` | Run 路径 |
| 产物点不开 | `file_proxy_rewrite` / `files.py` | 把 URL 改回绝对地址当补丁 |

### 19.4 wire 表双端一致

`wire.py` 是 SSOT。前端 **禁止手抄一份长期分叉的表**。

落地方式（选一，PR2 必须选）：

1. **推荐：** `patch_lobehub.py` apply `journal_transport` 时读 `gateway/runs/wire.py`，生成 Transport 里的 `const WIRE = {...}`。源只一份。
2. 次选：`gateway/runs/wire.json` 两边读，Python/TS 各 5 行加载。

测试：`tests/test_run_wire.py` 解析补丁生成结果或 json，与 `WIRE` 逐项相等。

`import_skill` 的 market/zip：Transport 里一行  
`apiName = state.identifier ? 'importFromMarket' : 'importSkill'`。  
不为此把 `wire.py` 升级成 factory。

---

## 20. 架构原则（可检验）

每条原则右边是 **检验手段**。不能检验的原则下一轮删掉。

| # | 原则 | 检验 |
|---|---|---|
| P1 | 一本账 | 不存在第二种事件类型模块（无 `timeline/types.py`） |
| P2 | 磁盘与线上同形 | 同一 `stamped_to_record`；契约测试逐字段 |
| P3 | 翻译一次、在门口 | gateway 测试禁止 import StreamChunk；Transport 禁止再 dispatch 自制协议块 |
| P4 | 状态出厂 | live 上 `plugin_state` == jsonl 上 `plugin_state`（深等） |
| P5 | 原生 UI | 不存在对 `Reasoning.tsx` / `StreamingHandler.ts` 的补丁 |
| P6 | 文件删除测试 | §5.1 每个文件能填「变化理由」表 |
| P7 | 无模块级可变会话表 | grep `_active_hubs` / 全局 `dict[str, RunSession]` 以外的平行索引为零（Registry 是唯一索引） |
| P8 | 一个 teardown | `finalize` 只有一处；resume/execute 都调用 |
| P9 | 前向兼容 | 前端对未知 `event` 不 throw；单测喂 `LlmCallStarted` 不断 |
| P10 | 定制可陈述 | 每个补丁的 `why` 能写成「上游缺 X」 |
| P11 | shim 不跑 Agent | `/v1/chat/completions` 对非 title 请求保持 400 |
| P12 | 相对文件 URL | live/jsonl 里无 `http://127.0.0.1:8765/files` |
| P13 | 断点可命名 | 人为制造 H3（先 close 再 running）时 doctor.broken_hop==H3 |

---

## 21. 稳定性：不变量比防御式代码重要

容易出 bug 的根因是 **双重真相** 和 **生命周期分叉**。本设计用不变量表替换 if 补丁。

### 21.1 生命周期不变量

```
create → (running | waiting_input)* → (completed | failed | canceled)
waiting_input  ⇒  tail 未 close、hub 未 close、snapshot/runnable 非空
completed|failed|canceled  ⇒  hub 已 close、inflight 已清、task done
cancel_requested  ⇒  最终状态是 canceled（finalize 里写死，不靠调用方记性）
```

HIL resume 是 `waiting_input → running`，仍走 **同一个** `finalize`。禁止 `_resume_run` 自写收尾。

### 21.2 投递不变量

```
subscribe 注册 先于 回放 先于 live     （无窗口丢事件）
jsonl.on_event 与 tail.on_event 由 Journal 同步扇出、同序
LiveTail 不做语义过滤
单投影器异常不中断 record（Hub 已隔离）
连续溢出 ≥3：踢订阅者 + error 日志，禁止静默
close 幂等；close 时 queue 满必须仍送出 sentinel
```

### 21.3 协议不变量

```
SSE event 名 == type(event).__name__ == jsonl.event_type
SSE id == stamped.seq
心跳无 id，不影响 Last-Event-ID
LiveGap 不是 Journal 事件，不得写入 jsonl
```

### 21.4 工具不变量

```
卡片字段 ⊆ ToolStarted/ToolInvoked.plugin_state ∪ SandboxOutputDelta
gateway 不得新增 plugin_state 键
arguments 给 transformToolCalls 用时，从 plugin_state 抽，不从截断 preview 猜
未知工具：不下发假 identifier，Transport 跳过（不要出一张废卡）
```

### 21.5 取消不变量

```
用户停止 ⇒ fetch aborted ∧ POST /runs/{id}/cancel
仅 abort 不断后端，算缺陷
仅 cancel 不 abort，算缺陷
```

### 21.6 故意不防御的地方

- 不在 LiveTail 过滤高频事件「以免打爆前端」——先忽略，带宽不够再加 **可观测的** mask，且 jsonl 仍全量。
- 不在 gateway 补齐残缺 `plugin_state`——残缺是出厂 bug，补会让出厂永远修不好。
- 不在 Transport 吞掉 `AgentRunFinished.error` 当成功——必须走 `ok: false`。

### 21.7 回归测试必须锁住的 bug 类

历史已经出过、重构后禁止再现：

1. 协议伪装（chat.completions 里塞 agent 流）
2. `plugin_state` 双重建造导致卡片字段时有时无
3. seed `tool.delta` 发两遍
4. 思考不建 `reasoning` operation → 手风琴不展开
5. 每个 delta 全量 `dispatchMessage({content, reasoning, tools})` 造成卡顿/丢订阅
6. abort 不 cancel，沙箱继续跑
7. HIL 走 finalize 把 tail 关掉，简历失败
8. 文档描述已删除的 `lca.events` 协议

每条对应一个测试名字，写在 `tests/test_run_invariants.py` 或现有文件里，PR2 结束必须齐。

---

## 22. 调用链：目标长度与禁止加跳

**现在（坏）：**  
`record → Hub → EventStreamProjector → EventStream → subscribe → Projection → Adapter → encode → HTTP → applyEvent → dispatchMessage`  
= **10 跳**，其中 4 跳在翻译同义句。

**目标：**

```
record → Hub.journal
            ├─ JsonlJournalProjector.on_event          磁盘
            └─ LiveTail.on_event
                 └─ GET /live  encode(stamped_to_sse_frame)
                      └─ JournalTransport.dispatch
                           └─ StreamingHandler.handleChunk
                                └─ 原生 setState
```

= **5 跳**（记账 1 + 分发 1 + 编码 1 + 映射 1 + 原生 1）。

硬规则：

- 从 `record()` 到磁盘，中间不得再有「翻译对象」。
- 从 `record()` 到套接字，中间不得再有「领域事件 DTO」。
- 想加一跳：先回答「这是新读者，还是新翻译？」新读者 → 新 Projector。新翻译 → 滚回 Transport。两者都不是 → 不准加。

`ObservabilityHub` 留着不是加跳，它是 Journal 的门面（OTel + 投影器列表 + 隔离）。Gateway 不准再包一层 Hub。

---

## 23. 效率：短链本身就是性能设计

### 23.1 删掉的成本

| 旧成本 | 为什么贵 | 目标 |
|---|---|---|
| 每个 `thinking.delta` 复制 tools Map + 整包 dispatch | O(工具数) × 思考 token 数 的 React 更新 | `onReasoningUpdate` 只改 reasoning；tools 不动 |
| Adapter 每条工具事件 `json.loads` + 重建 state | CPU + 分叉 | 透传 |
| Projection + Adapter 两套 `_invocation_ids` | 状态不同步 | 前端只用 Journal 的 `invocation_id` / `call_{id}` |
| `list.pop(0)` 环形缓冲（已在 EventStream 修过） | 保留 deque | LiveTail 继续 deque |

### 23.2 保留的成本（有意）

| 成本 | 理由 |
|---|---|
| jsonl 同步 `write + flush` | 一行 JSON，崩了不丢；异步消费者换来的是注册仪式和双路径 |
| SSE 上会流过前端忽略的 `LlmCall*` | 同形 > 省几 KB。真成为瓶颈再加 **显式 mask**，并打点 |
| `plugin_state` 比 preview 大 | 正确比小更重要；preview 是截断过的，不能画卡 |
| LiveTail 队列 256、缓冲 4096 | 思考流可能突发；溢出要可见，不要默默丢 |

### 23.3 前端更新预算

- reasoning：跟原生，随 token 更新（StreamingHandler 已如此）
- tools：跟原生 300ms throttle；`SandboxOutputDelta` 走 `onToolCallsUpdate`，吃同一 throttle
- 禁止在 Transport 里再写一套 throttle

### 23.4 测量口（重构后第一周看）

- `event_stream_subscriber_overflow`（改名 `live_tail_overflow`）是否还出现
- 单次 Run 的 live 字节数 vs jsonl 字节数（应近似，差在心跳）
- 长思考场景主线程：不应再出现「每次 delta 带全量 tools」的 profile

---

## 24. 对原生的修改点：牵扯面与升级风险

原则重申：能用契约表达的，不改上游。改上游的每一处必须能挨过一次 LobeHub minor 升级。

### 24.1 补丁分级

| 级 | 含义 | 升级时 |
|---|---|---|
| **A 协议入口** | 不打就无法把 Run 接进原生 handler | 锚点变了必须当天修，否则产品停 |
| **B 上游缺口** | 上游缺一个开关/一个 UI 孔 | 升级后先 verify，坏了只丢该能力 |
| **C 产品默认** | 默认模型/provider | 正则，通常稳 |
| **D 开发体验** | 无登录、局域网、路由 | 与生产协议无关，可滞后 |

### 24.2 每一补丁的牵扯面

| 补丁 | 级 | 改哪些上游文件 | 爆炸半径 | 失败形态 | 升级策略 |
|---|---|---|---|---|---|
| `journal_transport` | A | **只新增** `JournalTransport.ts`；改 `buildClientRuntimeHost.ts` 一处 `llm: new …` | 所有 Agent 对话 | 锚点 `ClientLLMTransport` 换名 → apply 失败，dev 起不来 | 锚点尽量短；host 文件大改时人肉看 10 行 |
| `call_llm_finalizer` | A | `callLlmFinalizer.ts` 一个布尔 | 所有 tool 收尾 | 上游改字段名 → 客户端重复跑工具（双执行） | verify marker `lcaClosedLoop`；必测「不发第二轮 tool」 |
| `file_proxy_rewrite` | A | `next.config.ts` rewrites | 产物 + Run API | Next 改 `defineConfig` 形状 → 无代理，404 | 独立小补丁，坏了只影响文件/入口 |
| `sandbox_generated_files` | B | `ExecuteCode/index.tsx` | 仅代码执行卡的产物条 | 卡片重构 → 产物不显示，对话仍在 | 可接受降级；不要把产物改写进答案 |
| `default_model` | C | `llm.ts` 常量 | 新会话默认模型 | 常量改名 → apply 失败 | 正则四条，稳 |
| `openai_guard` | B | `providers/openai/index.ts` | 仅 title/mini 等仍走 model-runtime 的请求 | 上游改 Responses 判断 → solo 误进 Responses | 与 Run 路径无关，坏了表现为标题失败 |
| `dev_auth_*` `lan_dev` `topic_route` | D | 认证/SPA/路由 | 本地开发 | 与 Run 无关 | 可整包延后 |

### 24.3 明确禁止的补丁（再出现就是架构回潮）

- `packages/model-runtime/**/openai.ts` / `qwen.ts` 抽 `lca.events`
- `fetchSSE.ts` / `protocol.ts` 加 `lca_tool_event`
- `StreamingHandler.ts` 加 LCA 分支（闭环用 finalizer 布尔，不用 handler 分叉）
- `Reasoning.tsx` / `Thinking` 改多段
- `ClientLLMTransport.ts` 加 LCA 特例（我们是 **替换** transport，不是在旧 transport 里开洞）

「替换 vs 开洞」：`buildClientRuntimeHost` 把 `llm` 换成 `JournalTransport`，`ClientLLMTransport` 保持上游原样。标题生成继续走后端 model-runtime，不经过这个 host。

### 24.4 升级 LobeHub 的标准动作（维护性）

```
1. sync_lobehub_ui.sh 拉新版本
2. patch_lobehub.py apply --reset
3. 失败的 apply = 锚点漂移，只修对应补丁，禁止顺手改协议
4. verify + doctor + drift
5. 手测：思考展开、一张 executeCode、停止、标题
```

drift guard 继续强制：`lobehub-ui/` 里没有补丁登记的改动 = CI 红。这是维护性的最后一道闸。

---

## 25. 代码规范（本子系统加严，不另起炉灶）

服从根目录 `AGENTS.md`，并加这些 **局部铁律**：

1. **禁止第三词表字符串。** grep 门禁：`thinking.delta` `timeline.v1` `lca_tool_event` `lca.events` 不得出现在 `gateway/` 与 `deploy/lobehub/patches/`（测试里的「不得出现」断言除外）。
2. **`wire.py` 无函数。** 只允许 `WIRE` 字面量 + `resolve()` 一行查表。PR review 见 `def` 除 `resolve` 外即拒。
3. **`live.py` 无 Starlette。**
4. **`execute.py` 无 `Request`。**
5. **方法 ≤80 行优先、硬顶 200；** `ingress.py` 用函数分段，不要类层次。
6. **公共函数全类型标注**；SSE data 在后端保持 `stamped_to_record` 的类型，不在 gateway 再定义平行 TypedDict。
7. **structlog，禁止 print。** 溢出、gap、cancel、finalize 失败都要有事件名。
8. **禁止裸 `except Exception`** 除非已有「记日志且不中断」的投影器隔离——新代码不要再抄一套。
9. **新全局可变状态禁止。** Registry 是唯一的 Run 索引。
10. **注释只写非显然约束**（例如「HIL 不得 close hub」）。禁止写「这里做投影」这种叙述。

---

## 26. 维护性：以后改东西只走一张表

| 我要… | 改哪里 | 不改哪里 |
|---|---|---|
| 新增 LCA 工具且 LobeHub 已有卡 | `tool_ui_state` 一行 builder + `wire.py` 一行；apply 补丁重生表 | Transport switch、gateway Adapter（已无） |
| 新增 LCA 工具且上游无卡 | 先做上游 builtin-tool，或接受无卡（文本结果） | 禁止在 Transport 里画自制 HTML |
| 新增 Journal 事件给 Langfuse | catalog + 出厂 `record()` | Transport（默认忽略） |
| 新增 Journal 事件要出现在聊天里 | catalog + Transport 映射表 **一行** | LiveTail、encode |
| 换第二个前端 | 新 Transport | gateway、Journal、wire |
| LobeHub 升级 | §24.4 | 协议 |
| 卡片缺字段 | `tool_ui_builders` | live、wire |
| 附件 SSRF 更严 | `ingest.py` | execute、Transport |

**认知负荷目标：** 新同事（或 Agent）读完 §3 心智模型 + §19 职责合同，应能在 15 分钟内指出「思考不展开」该打开哪个文件。做不到，就是文档或边界又脏了。

**文件数目标：** gateway 源文件 ≤16（§5.1）。新增第 17 个必须先通过删除测试并改本表。

---

## 27. 链路简图（给人和 Agent 钉在墙上）

```
[用户回车]
   │  LobeHub AgentRuntime（上游，不改）
   ▼
[JournalTransport]          前端唯一 LCA 入口
   │  POST /runs            开工
   │  GET  /runs/id/live    订账
   ▼
[runs/api] → [ingress] → [ingest]
   │
   ▼
[execute] 造 RunSession{hub, tail} → Agent/Team.record(...)
   │
   ├─ jsonl                 未来的自己
   └─ LiveTail → SSE        正在看的人
         │
         ▼
[JournalTransport.dispatch] 唯一翻译
         │
         ▼
[StreamingHandler]          上游，不改
         │
         ▼
Thinking / 工具卡 / 正文     上游，不改
```

中间没有虚线、没有「视情况走 A 或 B」。title 走右边另一条路（`openai_shim`），两路不相交。

---

## 31. 业界范式：我们站在哪，差在哪，补什么

对照的是 **「人看 Agent 干活」这条产品链路**，不是再争论 Journal vs Span（那是 ADR-0037 已定的）。

| 范式 | 他们怎么让人知道「断在哪」 | 我们现在 | 本重构后 |
|---|---|---|---|
| **LobeHub「过程即数据」** | 执行记录是主数据，UI 是投影 | Journal 是主数据，但 UI 走了第三套词表，对不上 | SSE = Journal 行，对齐这条范式 |
| **LangSmith / AgentOps replay** | 一次 run 一份可回放事件流；出问题打开那次 run | jsonl 有，无「把这次 run 的健康说成人话」的口 | `GET /runs/{id}/doctor` + jsonl 回放 |
| **OpenAI Agents tracing** | `agent` / `handoff` / `tool` / `generation` 一等事件 | Journal 词表已有对应物；UI 侧看不见类名 | live `event:` 就是类名，curl 即 trace |
| **OpenInference / OTel GenAI** | 内部模型自有，对外导出标准 | `OtelProjector` → Langfuse 已有 | 不动。live 不改造成 span，避免双协议 |
| **HTML5 EventSource** | `id` + `Last-Event-ID` 重连 | 后端认，前端不用 | Transport 必须带头 |
| **Vercel AI SDK Data Stream** | 类型化 SSE part，devtools 按 part 查 | 我们曾发明 `timeline.v1` 仿一套 | 用领域事件名，比通用 `text-delta` 更好查 |
| **Honeycomb 宽事件** | 一条事件带齐 `trace_id/run_id/seq/hop`，查询优先 | 日志字段不齐，hop 未命名 | 每条 structlog + doctor 字段带 `hop` `run_id` `seq` |
| **SRE 金信号 / 分层探针** | 每一跳有红绿，不是一条「500」 | `/health` 只有 `llm_available` | 五跳探针表 + doctor 裁决 |
| **LobeHub agent-tracing CLI** | 用 operation/message 拉快照 | 消息上没有 `run_id`，对不上 jsonl | `metadata.lca.run_id` 写进助手消息 |

**明确不抄：**

- 不为五跳同进程链路再上 Jaeger。那是给微服务的，这里加的是噪声。
- 不让浏览器每条事件 ACK 回服务器。聊天热路径不能再加一轮 RPC。
- 不把 Langfuse 当运行时依赖。Langfuse 挂了，doctor 和 jsonl 仍能指出断点。

**一句话对齐：** 业界共识是「结构化执行日志是真相，视图是投影，诊断是对日志的查询」。我们缺的不是更多层，而是 **把五跳变成可查询的探针**。

---

## 32. 五跳探针：不翻代码，说出 broken 在哪

给每一跳一个稳定名字。人和 Agent 只使用这些名字，禁止再用文件名当诊断词。

```
H0  client_send     浏览器发出 POST /runs
H1  run_accepted    202，有 run_id；session 进 registry
H2  journal_write   jsonl 出现事件（至少 AgentRunStarted）
H3  live_tail       LiveTail.last_seq 跟上 jsonl；有订阅者（若有人在看）
H4  sse_deliver     浏览器读到带 id 的 SSE 帧
H5  ui_map          Transport 把帧喂进 StreamingHandler；原生 UI 更新
```

判定规则是 **谓词**，不是经验：

| 现象 | 裁决 |
|---|---|
| 无 `run_id` / POST 非 2xx | **H0/H1**。看 HTTP 状态：503=`llm_unavailable`，400=ingress |
| 有 `run_id`，jsonl 不存在或 0 行 | **H2**。execute 没跑起来或路径写错 |
| jsonl 有事件，`doctor.live.last_seq` < jsonl `last_seq` 且已 close | **H3**。tail 关早了，或溢出踢订阅者（看 `evicted` 计数） |
| doctor 显示 live 健康，浏览器 10s 无第一帧 | **H4**。rewrite / 代理 / Last-Event-ID / 连接被掐 |
| curl live 看得到 `ToolStarted`，卡片没有 | **H5**。映射表 / wire / `transformToolCalls` |
| 卡片有，缺 `code`/`stdout` | **不是链路上的 hop**。出厂 `plugin_state`（layer1）。doctor 会标 `factory` |
| jsonl 有 `AgentRunFinished.error` | **H2 以内的业务失败**（模型/工具），不是转播坏了 |

「工厂 vs 链路」必须分开：链路是 hops；卡片字段是出厂。doctor 同时给两个 verdict，避免有人在 Transport 里修 `stdout`。

### 32.1 人怎么查（三分钟，零读源码）

```bash
# 1. 这次 run 怎么样？
curl -s localhost:8765/runs/$ID/doctor | jq .

# 2. 账本里有什么？
jq -c '{seq,event_type}' traces/runs/$ID.jsonl

# 3. 线上是不是同一本账？
curl -N -H "Last-Event-ID: 0" localhost:8765/runs/$ID/live | head
```

`doctor.verdicts[].hop` 即答案。附录 B 升级为这一套，删掉「打开 Adapter」。

### 32.2 Agent 怎么查（给另一个 Agent 的合同）

Agent 不允许被要求「去读 `lobehub_adapter.py`」。它只许：

1. `GET /runs/{id}/doctor` → JSON
2. 若需证据：`GET /runs/{id}` + jsonl 路径（doctor 里带回）
3. 跑门禁：`uv run pytest tests/test_run_invariants.py tests/test_run_wire.py -q`

doctor 的 JSON 必须稳定，字段当 API 版本化（`doctor.v1`），Agent 才能当工具调。

---

## 33. `GET /runs/{id}/doctor` —— 自动指认

这是一个 **新读者**（读 jsonl + session），不是热路径上的第六跳。纯函数：

```python
def diagnose(session: RunSession | None, jsonl_path: Path) -> DoctorReport: ...
```

HTTP 只是包一层。session 已从 registry 消失时，仍能只靠 jsonl 给出 H2 结论。

### 33.1 报告形状（`doctor.v1`）

```json
{
  "schema": "doctor.v1",
  "run_id": "run_...",
  "trace_id": "trace_...",
  "status": "failed",
  "broken_hop": "H3",
  "summary": "jsonl last_seq=84 but live closed at 12; evicted=1",
  "hops": {
    "H1": {"ok": true, "detail": "accepted"},
    "H2": {"ok": true, "last_seq": 84, "counts": {"ToolStarted": 2, "ReasoningDelta": 40}},
    "H3": {"ok": false, "last_seq": 12, "closed": true, "subscribers": 0, "evicted": 1},
    "H4": {"ok": null, "detail": "server cannot see browser"},
    "H5": {"ok": null, "detail": "server cannot see UI"}
  },
  "jsonl_path": "traces/runs/run_....jsonl",
  "consistency": {"jsonl_seq_eq_tail_seq": false},
  "factory": {
    "tools_missing_plugin_state": ["web_search"],
    "ok": false
  }
}
```

规则：

- `broken_hop` = 第一个 `ok: false` 的 hop。全绿则为 `null`。
- H4/H5 服务端 **标 `ok: null`**，不装懂。前端超时/失败时用同一 schema 填这两格（见 §34）。
- `factory.ok=false` 不覆盖 `broken_hop`；并列，避免误诊。
- `counts` 来自扫 jsonl，O(n) 可接受（单次 run 通常 <1 万行）。

### 33.2 服务端能自动抓住的故障（不用人看）

finalize 时跑一次 `diagnose`，`broken_hop` 非空或 `factory.ok=false` 则打：

```
run_doctor_verdict  run_id=... broken_hop=H3 summary="..."
```

这些情况必须自动亮：

| 条件 | broken_hop / factory |
|---|---|
| 终态 completed 但 jsonl 无 `AgentRunFinished`/`TeamRunFinished` | H2 |
| status=running 超过阈值且 jsonl 仍 0 行 | H2 |
| `evicted > 0` | H3 |
| `closed && status in {running, waiting_input}` | H3 |
| `ToolStarted` 而无 `plugin_state` 或 state 空 dict | factory |
| `ToolStarted` 无配对 `ToolInvoked`/`ToolDenied` 且已终态 | H2（工具没收尾） |

**不**在 finalize 里再投影一遍 UI。只写日志 + 可选 `traces/runs/{id}.doctor.json`（覆盖写）。Agent 查文件即可，不必 gateway 还活着。

### 33.3 `/health` 升级（进程级，不是某次 run）

```json
{
  "status": "ok",
  "llm_available": true,
  "runs": {"pending": 0, "running": 1, "waiting_input": 0},
  "live": {"total_subscribers": 1, "total_evicted": 0}
}
```

进程级红灯：`llm_available=false`、`total_evicted` 持续涨。不替代 doctor。

---

## 34. 前端可观察：同一套 hop 名

JournalTransport **禁止**再发明一套错误文案。用户/控制台看到的必须能对上 doctor。

1. `POST` 回来立刻把 `run_id` 写入助手消息 `metadata.lca = { run_id, trace_id, hop: "H1" }`。
2. 每收到一帧（可抽样：首帧、每种 event 首次、每 50 帧）：`hop: "H4"|"H5"`，`last_event`，`seq`。
3. 10s 无第一帧：`hop: "H4"`，`summary: "no SSE frame"`，控制台 `lca.hop` 一条结构化 log；消息 error 用同一 `summary`。
4. 映射失败（未知 wire、handler throw）：`hop: "H5"`。
5. 终态若失败：用 `run_id` 再 `GET /runs/{id}/doctor`，把服务端 `broken_hop` 覆盖显示（服务端能看见的 hop 比客户端准）。

控制台约定（人和 Agent 用浏览器 log 也能搜）：

```
lca.hop  hop=H4 run_id=run_... seq=12 event=ToolStarted mapped=tool_calls
```

`mapped=skip` 表示故意忽略（Delegation* 等）。若本该映射的事件出现 `skip`，就是 H5 表漏了——可用单测锁「白名单事件不得 skip」。

**不要做：** 独立诊断页、WebSocket 再推 doctor。消息 metadata + 控制台 + HTTP doctor 三件套够了。

---

## 35. 自动校验：三道闸，缺一不可

诊断告诉你「这次断在哪」。闸门告诉你「这种断法不许进 main」。

### 35.1 构建期（CI，每次改代码）

| 闸 | 抓什么 |
|---|---|
| `test_run_invariants.py` | 磁盘/线上同形；无第三词表；相对 URL；未知事件不抛；finalize 一处 |
| `test_run_wire.py` | 生成的 TS 表 == `wire.py` |
| `test_run_import_boundaries.py` | §17.1 依赖 |
| `test_run_doctor.py` | 给定伪造 jsonl+session，`broken_hop` 符合 §32 谓词 |
| `test_sse_journal_projector.py`（已有） | `event:` == 类名 |
| grep 门禁 | `thinking.delta` `timeline.v1` `lca.events` `lca_tool_event` |
| `patch_lobehub.py verify` + `drift` | 补丁还在；无未登记改动 |
| ruff / lint-imports / mypy / pytest / vulture | 原流水线 |

### 35.2 运行期（每次 Run，自动）

| 闸 | 动作 |
|---|---|
| finalize `diagnose` | 非空 `broken_hop` → `run_doctor_verdict` error 级日志 |
| LiveTail 溢出 | 已有 `live_tail_overflow` / evict；计入 doctor |
| Transport 首帧超时 | 用户可见 H4，不转圈到死 |
| 可选落盘 `*.doctor.json` | 死后仍可查 |

运行期闸 **不得** throw 打断用户收尾。只报告。

### 35.3 发布期（人/Agent 升 LobeHub 或改协议）

spec §24.4 五步，外加：

```
curl -s localhost:8765/health | jq .llm_available
# 打一条带工具的对话后
curl -s localhost:8765/runs/$ID/doctor | jq '{broken_hop,factory,summary}'
```

`broken_hop==null && factory.ok` 才算发布过关。这比「我觉得卡片亮了」可交给 Agent。

### 35.4 契约测试即说明书

测试函数名必须能当目录：

```
test_doctor_flags_h3_when_tail_closes_while_running
test_doctor_flags_factory_when_tool_started_without_state
test_live_frame_matches_jsonl_record
test_transport_does_not_skip_tool_started
test_abort_calls_cancel_endpoint
```

Agent 搜 `H3` 应能落到测试，而不是落到一篇散文。

---

## 36. 可调试性设计约束（防止观测再变考古）

1. **同一 `run_id` 贯穿** jsonl 文件名、doctor、SSE data.scope、消息 metadata、structlog、Langfuse。缺一处即 bug。
2. **hop 名是封闭枚举** `H0..H5`。日志里禁止 `step1`/`phase_a` 这种临时名。
3. **doctor 是纯函数**，单测不启 HTTP。
4. **热路径不加诊断 RPC。** doctor 按需拉；finalize 写一笔日志即可。
5. **H4/H5 服务端承认看不见。** 假装看见比缺失更糟。
6. **Langfuse 是投影，不是排障入口。** 排障入口是 doctor + jsonl。Langfuse 挂了不得导致「无法判断断在哪」。
7. **禁止为了好看把 doctor 做成第二个 UI 协议。** 它是运维合同，不是 timeline.v2。

---

## 28. Key Decisions

1. **词表两套，翻译一次，地点在 Transport。** Journal 是后端契约；LobeHub 类型跟上游走。第三套 `timeline.v1` 是认知税。
2. **SSE 帧 = `stamped_to_sse_frame`。** jsonl 与线上同一形状；`curl` 即 debugger。
3. **LiveTail 是 JournalProjector，不是平行总线。** 新增视图 = 新增投影器。
4. **jsonl 用已有同步投影器。** 一行 JSON + flush，不值得异步消费者。
5. **plugin_state 出厂即真相。** gateway 再造必分叉。
6. **思考跟原生一块手风琴、本轮覆盖。** 不在 Reasoning 上打时间线补丁。
7. **委派不进答案。** 正文是答复，不是协作旁白。
8. **定制最小集：闭环 + 坐标表 + 文件代理 + 产物条。** 其余是旧协议残骸。
9. **openai_shim 永不为 Agent 服务。** 两种问题，两条路。
10. **分四刀，PR2 前后端同发。** 协议切换不能裂开。
11. **变化轴不存在就不加间接层。** 拒绝 gateway Strategy 拼 state、Sanitizer 链、假想中立 DTO。
12. **文件 URL 保持相对 `/files/{id}`。** Next rewrite 同源代理；删除 `absolutize` 与浏览器侧 `LCA_GATEWAY_PUBLIC_URL` 依赖。
13. **`wire.py` 是 SSOT，补丁 apply 时生成前端表。** 禁止长期手抄双表。
14. **替换 Transport，不在 `ClientLLMTransport` / `StreamingHandler` 开洞。** 升级时锚点只剩 host 里一处 `new`。
15. **未知 Journal 事件前端忽略。** 前向兼容；过滤不放 LiveTail。
16. **依赖方向可 lint。** `live.py` 无 Starlette，`wire.py` 无函数，`execute.py` 无 `Request`。
17. **调用链硬顶 5 跳。** 新跳必须是新读者或门口翻译，否则拒绝。
18. **五跳探针 + `doctor.v1` 是排障入口。** 人和 Agent 先看 `broken_hop`，不先翻源码。Langfuse 不是排障入口。
19. **H4/H5 服务端标 `ok: null`。** 不假装看见浏览器。前端超时用同一 hop 名回填。
20. **finalize 自动跑 diagnose，只打日志不抛。** 热路径不加诊断 RPC。
21. **Langfuse 只经 `create_observability` 挂上。** 有凭据则加入读者名单；SDK/凭据缺失则跳过，不阻断 Run。禁止 `ObservabilityHub([])` 手造。

---

## 29. Open Questions

产品点已收成决定（思考覆盖、委派不出正文、HIL UI 后置、相对文件 URL、wire 生成）。执行前只需确认：

- 是否接受 **PR2 前后端必须同发**（不能灰度两套协议）？
- `import_skill` 的 market 分叉用 Transport 一行 if，是否可接受？

若无异议，按 §11 / 施工文档开干。

---

## 30. PR Plan（给执行切片用）

| PR | 标题 | 影响 | 依赖 |
|---|---|---|---|
| 1 | `refactor(gateway): LiveTail as Journal projector, jsonl back to hub` | `run_executor.py` `run_registry.py` `runs/live.py`（新）`event_stream.py`（适配层暂留） | 无 |
| 2 | `feat: Journal SSE + JournalTransport, delete timeline.v1` | `gateway/timeline/**` 删、`lobehub_bridge` 迁、`journal_transport` 补丁、`CUSTOMIZATIONS.md` | PR1 |
| 3 | `refactor: POST /runs, drop /v1/agent/*, docs` | `app.py` `file_proxy_rewrite` 文档 ADR-0053 文首 | PR2 |
| 4 | `feat: HIL waiting_input in UI`（可选） | Transport + 少量 UI | PR2 |

---

## 附录 A：从现在到目标的对照（防迷路）

| 现在 | 目标 | 动作 |
|---|---|---|
| `EventStream` | `LiveTail(JournalProjector)` | 改接口，留算法 |
| `_jsonl_consumer` | `JsonlJournalProjector` | 删除前者 |
| `_active_hubs` | `session.hub` | 删除前者 |
| `TimelineProjection` | （不存在） | 删除 |
| `LobeHubSSEAdapter` | `wire.py` 一张表 | 删除前者 |
| `timeline.v1` 事件名 | Journal 类名 | 删除前者 |
| `AgentTimelineTransport.applyEvent` | `JournalTransport` + `StreamingHandler` | 替换 |
| `thinking.delta` 拼接多段 | 本轮 reasoning 覆盖 | 行为变更，有意 |
| 委派 Markdown | 忽略 | 行为变更，有意 |
| `/v1/agent/runs/.../timeline` | `/runs/{id}/live` | PR3 |

## 附录 B：人与 Agent 排障口令（先 doctor，再证据）

```
# 断在哪一跳？
curl -s localhost:8765/runs/$ID/doctor | jq '{broken_hop,summary,factory,hops}'

# 账本
jq -c '{seq,event_type}' traces/runs/$ID.jsonl

# 线上是否同一本账
curl -N -H "Last-Event-ID: 0" localhost:8765/runs/$ID/live | head

# 进程活着吗
curl -s localhost:8765/health | jq .
```

`broken_hop=H2` → 执行/record。`H3` → LiveTail/finalize。`H4` → rewrite/连接。`H5` → Transport 映射。`factory.ok=false` → `tool_ui_state`。不要翻已删除的 Adapter。
