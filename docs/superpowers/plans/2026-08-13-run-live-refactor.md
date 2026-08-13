# Run Live Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「人看 Agent 干活」收敛成：一本 Journal、两个读者（jsonl + LiveTail）、一次翻译（JournalTransport → StreamingHandler）。废掉 timeline.v1 与一切平行词表。

**Architecture:** Journal 是唯一真相。`LiveTail` 是 `JournalProjector`，不是总线。SSE 帧 = 已有 `stamped_to_sse_frame`（事件类名 = jsonl `event_type`）。前端不再私造 `applyEvent`，只喂 LobeHub 原生 `StreamingHandler`。`plugin_state` 出厂即用，gateway 只保留一张 wire 坐标表。

**Tech Stack:** Starlette gateway, existing layer0 journal projectors, LobeHub `StreamingHandler` / `ClientLLMTransport` callbacks, patch engine under `deploy/lobehub/patches/`.

**Spec:** `docs/superpowers/specs/2026-08-13-run-live-architecture-design.md`

**Invariant after every PR:** 用户仍能发一条消息，看见思考和工具卡（PR1 保持旧帧；PR2 起换成 Journal 帧，前后端同发）。

**Architecture constraints (spec §16–27, 不可在施工时「灵活变通」):**

- 调用链硬顶 5 跳；禁止再引入 DTO / 平行总线 / gateway 侧 `build_*_state`
- `live.py` / `doctor.py` 无 Starlette；`wire.py` 仅查表；`execute.py` 无 `Request`
- 排障入口是 `GET /runs/{id}/doctor` 的 `broken_hop`，不是翻源码
- 文件 URL 保持相对 `/files/{id}`，删除 `absolutize_*`
- `wire.py` apply 时生成前端表；禁止手抄双表
- 替换 `JournalTransport`，禁止改 `StreamingHandler` / `ClientLLMTransport` / `Reasoning.tsx`
- 原则 P1–P12 必须能落成测试或 grep 门禁

**Verify after every PR:**

```
uv run ruff check --fix . && uv run ruff format .
uv run lint-imports
uv run mypy lca gateway
uv run pytest
uv run vulture lca gateway --min-confidence 80
```

---

## File map (target, after PR3)

**Create**

- `gateway/runs/__init__.py`
- `gateway/runs/live.py` — `LiveTail(JournalProjector)`
- `gateway/runs/doctor.py` — `diagnose()` → `doctor.v1`
- `gateway/runs/api.py` — HTTP create/live/get/cancel/answer
- `gateway/runs/session.py` — 从 `run_registry.py` 迁入
- `gateway/runs/execute.py` — 从 `run_executor.py` 迁入并削皮
- `gateway/runs/ingress.py` — 从 `lobehub_bridge/{parser,conversation,prepare}` 合并
- `gateway/runs/ingest.py` — 从 `lobehub_bridge/{file_ingest,ingest_cache,url_policy,settings,file_urls}` 合并
- `gateway/runs/wire.py` — 纯坐标表
- `gateway/cors.py` — 现 `_http.py`
- `gateway/modes.py` — 现 `mode_catalog.py`
- `gateway/assemble.py` — 现 `team_factory.py`
- `gateway/openai_shim.py` — 现 `openai_compat_api.py`
- `gateway/files.py` — 从 `app.py` 拆出
- `deploy/lobehub/patches/runtime/journal_transport.py`
- `docs/run-live.md`

**Delete (by PR2/PR3)**

- `gateway/event_stream.py`
- `gateway/timeline/` 整包
- `gateway/lobehub_bridge/` 整包
- `gateway/run_executor.py` `run_registry.py` `mode_catalog.py` `team_factory.py` `_http.py`（迁完再删）
- `deploy/lobehub/patches/runtime/agent_timeline_transport.py`
- `deploy/lobehub/patches/streaming/`
- `docs/agent-timeline.md`

**Do not touch**

- `lca/layer1_cognitive/body/tool_ui_state.py`
- `lca/layer0_infra/observability/journal/` 事件类型（可用 `stamped_to_sse_frame`）
- Agent/Team 运行时

---

## Chunk 1: PR1 — LiveTail + Hub 双读者（协议不变）

### Task 1: LiveTail 契约测试

**Files:**
- Create: `tests/test_live_tail.py`
- Create: `gateway/runs/__init__.py`
- Create: `gateway/runs/live.py`

- [ ] **Step 1: 写失败测试**

覆盖：
- `LiveTail` 是 `JournalProjector`（有 `on_event` / `flush` / `close`）
- `on_event` 后 `subscribe(after_seq=0)` 能读到同一条 `StampedEvent`（对象，不是翻译后的 dict）
- 先 `subscribe` 再 `on_event`：live 不丢
- `subscribe(after_seq=N)` 不回放 `seq<=N`
- 缓冲被淘汰后 `subscribe` 首条是 gap 信号（类型名 `LiveGap` 或 `GapEvent`，spec 用 `LiveGap`）
- `close()` 后订阅结束；二次 `close` 幂等
- 连续 queue full ≥3 次踢掉该订阅者，且有 structlog（可用 caplog）

参考算法：现 `gateway/event_stream.py`。不要从 subscribe 里做 RunInsight 过滤。

- [ ] **Step 2: 实现 `LiveTail`，测试绿**

`gateway/runs/live.py` 只做分发。把 `event_stream.py` 的 deque/溢出策略搬过来，实现 `JournalProjector`。

- [ ] **Step 3: 加 import 边界测试骨架**

`tests/test_run_import_boundaries.py`：断言 `gateway/runs/live.py` 的源码不含 `starlette`。后续任务往同一文件加白名单。

- [ ] **Step 4: Commit**

```
git add tests/test_live_tail.py tests/test_run_import_boundaries.py gateway/runs/live.py gateway/runs/__init__.py
git commit -m "feat(gateway): LiveTail journal projector for live subscribers"
```

### Task 2: Session 持有 hub + tail；jsonl 回到投影器

**Files:**
- Modify: `gateway/run_registry.py`（或先写 `gateway/runs/session.py` 再让旧文件 re-export）
- Modify: `gateway/run_executor.py`
- Modify: `gateway/app.py` `_resume_run` 用 `session.hub` 而非 `_active_hubs`
- Test: `tests/test_gateway_cancel_observability.py` `tests/test_timeline_projector.py` 及相关 gateway 测试必须仍绿

- [ ] **Step 1: `RunSession` 增加 `hub` + `tail`，去掉对平行 `stream: EventStream` 的依赖**

过渡：`session.stream` 属性可以是 `session.tail` 的别名，避免一次改完所有引用。

- [ ] **Step 2: `create_run_session` 改为**

```python
tail = LiveTail()
hub = ObservabilityHub(
    [],
    policy=AttributePolicy(ObservabilitySettings().verbosity),
    journal_projectors=[
        JsonlJournalProjector(jsonl_path),
        tail,
    ],
)
session = RunSession(..., hub=hub, tail=tail)
```

删除：`_jsonl_consumer`、`_jsonl_tasks`、`_EventStreamProjector`、`_active_hubs`、`aiofiles` 路径。

- [ ] **Step 3: `_finalize_run(session, registry, workspace, success)` 不再传入游离 hub**

`hub.close()` 走 `session.hub`。`LiveTail.close` 由 projector `close` 触发（`LiveTail.close` = 现 EventStream.close）。

- [ ] **Step 4: `_resume_run` 用 `session.hub`，删除 `app.py` 对 `_active_hubs` 的 import**

- [ ] **Step 5: 跑 gateway / timeline / cancel 相关测试，全绿后 commit**

```
git commit -m "refactor(gateway): journal jsonl and live tail are hub projectors"
```

### Task 3: 旧 timeline 管道改从 LiveTail 读（帧不变）

**Files:**
- Modify: `gateway/timeline/routes.py` `gateway/timeline/stream.py`

- [ ] **Step 1: `compose_sse_stream` 的输入改为 `LiveTail.subscribe`**

若 `LiveTail` 与 `EventStream` 方法同构，只换类型。输出仍是 timeline.v1（Projection + Adapter），**前端零改动**。

- [ ] **Step 2: 删除 `gateway/event_stream.py`（确认无引用）**

- [ ] **Step 3: 全量 pytest + 手测一条带思考的对话（若本机有 LLM）**

- [ ] **Step 4: Commit**

```
git commit -m "refactor(gateway): timeline SSE reads LiveTail, drop EventStream"
```

### Task 3b: doctor 纯函数 + HTTP（PR1 即可，不改线上帧）

**Files:**
- Create: `gateway/runs/doctor.py`
- Create: `tests/test_run_doctor.py`
- Modify: `gateway/app.py` 或 `runs/api.py` 注册 `GET /runs/{id}/doctor`
- Modify: `execute.finalize` 调用 `diagnose`，只打 `run_doctor_verdict` 日志

- [ ] **Step 1: 失败测试锁谓词**

`test_doctor_flags_h3_when_tail_closes_while_running`  
`test_doctor_flags_factory_when_tool_started_without_state`  
`test_doctor_broken_hop_is_first_false`  
`test_doctor_works_from_jsonl_without_session`

- [ ] **Step 2: `diagnose()` 无 Starlette；HTTP 薄包。`schema=doctor.v1`**

- [ ] **Step 3: Commit**

```
git commit -m "feat(gateway): run doctor names the broken hop"
```

**PR1 完成标准：** 前端仍走 `/v1/agent/runs` + timeline.v1；进程内已无平行总线；jsonl 仍完整；`GET /runs/{id}/doctor` 可用。

---

## Chunk 2: PR2 — Journal 帧 + JournalTransport（协议切换，前后端同发）

### Task 4: 纯函数映射表（后端可测的那一半）

**Files:**
- Create: `gateway/runs/wire.py`
- Create: `tests/test_run_wire.py`
- Modify: 暂时让 `LobeHubSSEAdapter` 改调 `wire.py`（若还活着）——更好：映射测试不依赖 Adapter

- [ ] **Step 1: `wire.py` 按 spec §6.4 落地，测试锁满表**

`resolve_wire("execute_code") == ("lobe-cloud-sandbox", "executeCode")`。未知工具返回 `None`。文件中除 `resolve` 外不得有其它 `def`。

- [ ] **Step 2: Commit**

```
git commit -m "feat(gateway): tool wire coordinate table only"
```

### Task 5: `GET /runs/{id}/live` 发 Journal 帧

**Files:**
- Create: `gateway/runs/api.py`（可先只加 live，create 仍走旧 routes）
- Modify: `gateway/app.py` 注册 `GET /runs/{id}/live`
- Test: `tests/test_run_live_sse.py`（新）

- [ ] **Step 1: 失败测试**

用 scripted/mock LLM 或直接 `tail.on_event(stamped)`：
- live 的 `event:` 是 `ReasoningDelta` / `ToolStarted`，不是 `thinking.delta`
- `data` 能 `json.loads` 且含 `event_type`，与 `stamped_to_record` 同构
- `ToolStarted` 的 `plugin_state` 未被改写
- 空闲可测心跳较难，单测 `compose` 超时发 `: keepalive` 即可
- `Last-Event-ID: 2` 不重放 seq 1

复用 `lca.layer0_infra.observability.journal.sse_frames.stamped_to_sse_frame`。禁止新写 encode。

- [ ] **Step 2: 实现 live handler + 心跳循环（从现 `compose_sse_stream` 抄 wait_for，但不要 Projection/Adapter）**

- [ ] **Step 3: Commit**

```
git commit -m "feat(gateway): GET /runs/{id}/live emits journal SSE frames"
```

### Task 6: JournalTransport 补丁

**Files:**
- Create: `deploy/lobehub/patches/runtime/journal_transport.py`
- Delete after cutover: `deploy/lobehub/patches/runtime/agent_timeline_transport.py`
- Modify: `call_llm_finalizer` 的 `depends_on` 改为 `journal_transport`
- Modify: `deploy/lobehub/CUSTOMIZATIONS.md`（本 PR 后半同步）

- [ ] **Step 1: 对照 `ClientLLMTransport.runAttempt` 抄 callbacks**

必须接上：
- `onReasoningStart` → `startOperation({ type: 'reasoning' })`
- `onReasoningComplete` → `completeOperation`
- `onReasoningUpdate` / `onContentUpdate` / `onToolCallsUpdate`
- `toggleToolCallingStreaming`
- `transformToolCalls`

数据源换成 `POST /lca-api/v1/agent/runs`（PR2 期间 **保持旧 URL**，避免和下一切口纠缠）但 **改 GET live**：

过渡 URL 策略（选这个，减少 PR2 变量）：

- 仍 `POST /lca-api/agent/runs`（rewrite 到现 `/v1/agent/runs`）
- `GET /lca-api/runs/{id}/live` 需要 rewrite 到 gateway `/runs/{id}/live`

因此 PR2 **必须**在 `file_proxy_rewrite` 增加一条：

```
{ source: '/lca-api/runs/:id/live', destination: `${base}/runs/:id/live` }
```

原 `/lca-api/:path*` → `/v1/:path*` 不要删（POST create 还靠它）。

- [ ] **Step 2: `dispatch(handler, frame)` 只实现 spec §6.3 表**

`ToolStarted`：
```
function.name = `${identifier}____${apiName}`  // 来自前端内嵌的同一张 wire 表
arguments = JSON.stringify(pickArgs(plugin_state | arguments))
```
然后 `handler.handleChunk({ type: 'tool_calls', tool_calls, isAnimationActives })`。

`SandboxOutputDelta` / `ToolInvoked`：不要新 chunk 类型；拿 handler 已有 tools，改 `result.state`，`onToolCallsUpdate`。

本轮思考替换：见 spec §6.5，工具之后新建 `StreamingHandler`。

abort：`fetch` signal aborted 后 `POST /lca-api/runs/{id}/cancel`（rewrite 已有 `/runs/{id}/cancel` 不经 `/v1`——确认 `app.py` 路由；若只有 `/runs/{id}/cancel`，加 rewrite 或 Transport 打绝对路径 `/runs/...` 经 file proxy）。

**Cancel 路径：** 现成 `POST /runs/{id}/cancel`。`file_proxy_rewrite` 已代理 `/files` 和 `/lca-api`。给 cancel 用：

```
fetch(`/runs/${runId}/cancel`, { method: 'POST' })
```

并在 next rewrite 加 `/runs/:path*` → gateway `/runs/:path*`，或走 `LCA_GATEWAY_PUBLIC_URL` 直连。优先 rewrite，避免 CORS。

- [ ] **Step 3: apply 时从 `wire.py` 生成 Transport 内嵌表**

`journal_transport.apply` 读 Python `WIRE`，写入 TS `const WIRE`。`tests/test_run_wire.py` 解析生成后的 TS（或 apply 后的目标文件）与 Python 逐项相等。禁止手抄。

- [ ] **Step 4: `python3 deploy/lobehub/patch_lobehub.py apply --reset && verify`**

- [ ] **Step 5: 手测（有 LLM / 有脚本）**

- 思考手风琴在流式时展开（`isMessageInReasoning`）
- executeCode 出原生卡，stdout 更新
- 产物条仍在（`sandbox_generated_files`）
- 停止后 gateway run 为 canceled
- 委派不再出现在答案正文

- [ ] **Step 6: 删除 `agent_timeline_transport.py`，改 host 只引 JournalTransport**

- [ ] **Step 7: Commit**

```
git commit -m "feat(lobehub): JournalTransport feeds native StreamingHandler"
```

### Task 7: 拆除 timeline 与 lobehub_bridge

**Files:** 见 File map 删除栏
- Modify: `create_agent_run` 暂留，内部已用新 session
- Move: ingress/ingest 合并到 `gateway/runs/ingress.py` `ingest.py`
- Tests: 改 import；`test_timeline_projector.py` 改为断言 live **不**翻译；`test_lobehub_tool_wire.py` 缩成 wire 表

- [ ] **Step 1: 搬迁 ingress/ingest，全量测试改 import 后绿**

- [ ] **Step 2: 删除 `gateway/timeline/`、`lobehub_bridge/`、Adapter、error_sanitizer、sse_encode**

`stream_agent_timeline` 若还要 deprecated：实现为 307/提示改 `/runs/{id}/live`，或直接让旧路径返回 Journal 帧（前端已不读 timeline.v1）。推荐旧路径也改发 Journal 帧，避免两套。

- [ ] **Step 3: 重写 `CUSTOMIZATIONS.md` 为 spec §5.2 最小表；`docs/agent-timeline.md` 改指向本 spec**

- [ ] **Step 4: 不变量与词表门禁**

`tests/test_run_invariants.py` 锁 spec §21.7：
- live `plugin_state` == jsonl `plugin_state`
- `gateway/` 与 `deploy/lobehub/patches/` 无 `thinking.delta` / `timeline.v1` / `lca.events`
- live data 里 `/files/` 不是 `http://127.0.0.1`
- 未知事件名不使映射函数抛
- `finalize` 只有一处定义

`test_run_import_boundaries.py` 补全：`wire.py` 不 import 其它 gateway 模块；`execute.py` 不含 `starlette`。

- [ ] **Step 5: vulture + pytest 全绿，commit**

```
git commit -m "refactor(gateway): delete timeline.v1 and lobehub adapter dual-state"
```

**PR2 完成标准：** curl live 看到 `event: ToolStarted`；UI 用原生 Thinking + 工具卡；仓库无 `thinking.delta` 字符串（测试夹具除外，应已改）。

---

## Chunk 3: PR3 — HTTP 削皮 + 文档

### Task 8: `POST /runs` 取代 `POST /v1/agent/runs`

**Files:**
- Modify: `gateway/runs/api.py` `gateway/app.py`
- Modify: `deploy/lobehub/patches/proxy/file_proxy_rewrite.py`
- Modify: `journal_transport` 的 POST URL → `/lca-api/runs` 或 `/runs`
- Modify: `docs/lobehub-integration.md` `docs/run-live.md`
- Modify: `docs/adr-0053-gateway-sse-architecture.md` 文首 Superseded

- [ ] **Step 1: `POST /runs` 与现 create 行为一致（202, inflight dedup）**

- [ ] **Step 2: rewrite**

```
/lca-api/runs           → /runs
/lca-api/runs/:path*    → /runs/:path*
/files/:path*           → /files/:path*
```

删除「先加 `/v1` 再剥」的旧规则。标题请求仍走 LobeHub backend → `OPENAI_PROXY_URL=/v1` → `openai_shim`，不动。

- [ ] **Step 3: 删除 `/v1/agent/runs*`；相关测试改路径**

- [ ] **Step 4: 文件重命名（可选同 PR 或紧随）：**

`_http.py`→`cors.py`，`mode_catalog.py`→`modes.py`，`team_factory.py`→`assemble.py`，`openai_compat_api.py`→`openai_shim.py`，`files` 从 `app.py` 拆出。每步改 import，lint-imports 绿。

- [ ] **Step 5: 删 `patches/streaming/`、死 pycache、过时 CUSTOMIZATIONS 段落**

- [ ] **Step 6: 文档三件套 + ADR-0053 superseded**

- [ ] **Step 7: doctor + verify + 全量测试，commit**

```
git commit -m "refactor(gateway): POST /runs is the only agent entry; retire timeline routes"
```

---

## Chunk 4: PR4（可选）— HIL

### Task 9: waiting_input 不关 tail；Transport 暴露状态

只在产品要 HIL 时做。架构上 PR2 已禁止 HIL 走 finalize/close。本任务是 UI。

- [ ] live 在 `WAITING_INPUT` 保持连接（已有则补测）
- [ ] Transport 读到暂停后不要当 error
- [ ] 提交 `POST /runs/{id}/answer` 后继续读同一 live（Last-Event-ID）

---

## Execution notes

- **PR2 不可拆成「先切后端再切前端」。** 中间 commit 可以在 branch 上，但不许单独进 main。
- 不要给 `StreamingHandler` 打补丁，除非发现 `transformToolCalls` 无法消化 `identifier____apiName`——那时只补坐标，不补协议。
- 发现某工具卡空白：去 `tool_ui_state` 补出厂 state，禁止在 `wire.py` 或 Transport 里拼字段。
- 不要复活 `lca.events`、`openai_stream`、`thinking.delta`。

---

## Definition of done

- [x] `gateway/timeline/` 不存在
- [x] `gateway/lobehub_bridge/` 不存在
- [x] `event: thinking.delta` 不存在于生产代码
- [x] `curl /runs/$ID/live` 的 event 名能在对应 jsonl 里 grep 到
- [ ] 思考块流式展开（原生 Thinking）— 代码已接 `onReasoningStart`，待带 LLM 手测
- [ ] 工具卡为原生 builtin Render — `ToolStarted` → `identifier____apiName`，待带 LLM 手测
- [x] 停止会 cancel 后端 run
- [x] 定制清单 ≤ spec §5.2
- [ ] 验证流水线全绿
