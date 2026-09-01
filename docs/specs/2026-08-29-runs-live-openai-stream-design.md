# RCA + Design: `/runs/{id}/live` 收敛到 OpenAI-compatible SSE

> 状态：Draft — 2026-08-29
> 范围：LobeHub UI ↔ LCA Gateway 的流式契约
> 目标：删除 ADR-0096 MVA、ADR-0097、ADR-0098 引入的自创 wire 与前端补丁，恢复"后端适配前端"。

## 1. 症状

- 用户报告：`runs/live` 收到的事件在 LobeHub 前端无法稳定显示
- LobeHub 大半时间不发即停，或需多次刷新
- Debug 涉及 : LLMStreamTap → LiveBus(ring+tail) → SessionEvent 5 类词汇 → 3 通道 SSE wire(`deltas`/`projection.*`/`terminal`) → EvidenceRunner(content_ref → `/evidence/{digest}`) → ts SDK 生成器 → TS 侧 `LcaRunDriver` 900 LOC → `lcaJournal` 480 LOC 翻译表
- 最近 6 个提交全都打在 wire 与补丁上,问题依旧

## 2. 根因(一次到位)

我们把"**单一可重放流**"与"**可订阅投影通道**"两个独立产物强行共用同一条 SSE 链(`session_adapter.py::stream_live` 三通道 fan-in),又为了后端的恢复语义把增量 token 推给了一个引用证据存储的独立通道(`/evidence/{digest}`)。结果是:

1. 状态机在双源泵 + 队列 + projectioin-via-activity 检测 terminal 三个东西上同时维护,任何一个慢一拍就悬挂
2. token 级流被 evidence 间接化,LLM 实时性严重受损(ADR-0098 §1 F1: SSE 非实时)
3. 前端驱动 480+ LOC 翻译 `deltas ↔ projection ↔ terminal`,加 `LcaRunDriver` 900 LOC 状态机,任何 wire 微调都令补东墙
4. SDK 自动生成器(消费侧 TS 来自 Python Schema)让 schema 成为另一套"事实",而非 SPEC.md

> 这是 architecture-level 问题(systematic-debugging §Phase 4.5)。继续打补丁只能越补越厚。

## 3. 决策(ADR-0099)

### D1. Wire 收敛到 OpenAI ChatCompletion streaming

```
POST /v1/chat/completions
Authorization: Bearer <agent-token>
Content-Type: application/json
Accept: text/event-stream

→ 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

data: {"id":"chatcmpl-...","object":"chat.completion.chunk","created":...,"model":"solo",
       "choices":[{"index":0,"delta":{"role":"assistant","content":"...","reasoning_content":"..."},
                   "finish_reason":null}]}\n\n
data: {"id":"chatcmpl-...","object":"chat.completion.chunk", ..., "choices":[{"...delta":{"tool_calls":[{"index":0,"id":"call_...","function":{"name":"...","arguments":"..."}}]}...}]}\n\n
data: {"id":"chatcmpl-...","object":"chat.completion.chunk","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n
data: [DONE]\n\n

: keepalive   (15s 空闲时的注释帧,无 event/data)
```

字段含义(全部为标准 OpenAI 扩展):
- `delta.content`: 助手文本增量
- `delta.reasoning_content`: 思考(token-by-token),LobeHub `openai.ts:474-478` 原生识别
- `delta.tool_calls`: OpenAI 函数调用增量。backend 已经在内部执行完 tool,这里只 emit "展示态" —— `id` 取自后端 tool span,`name` 取自 wire tool 名,`arguments` 取自最终 plugin_state(避免 LobeHub 试图本地执行)。LobeHub 渲染 tool 卡但不再 rerun。
- `finish_reason`: `stop` 终态,`tool_calls` 终结于下一轮工具
- `usage`: 终态 token 计数

不包含:
- 任何自定义 `event:` 名称空间
- 引用证据 `content_ref → /evidence/{digest}`
- 三类分轴 `id`(所有事件共享一个 SSE 链上的 `id:` 即可)

### D2. LobeHub 侧只保留最小 provider 注册

- 在 `model-runtime/openaiCompatibleFactory.createOpenAICompatibleRuntime()` 加一个 LCA provider,baseURL 指向 `${LCA_HOST}/v1`,apiKey 用 `NEXT_PUBLIC_LCA_TOKEN`
- `lca_model_catalog` patch 现在变成: 把 `solo / team / auto` 三个 model 标到这个 provider
- `streamingExecutor.ts` 不用动模型运行时路径(它已经是 `executeClientAgent → runLcaJournal → finishLcaChat` 这套壳,但因为我们走 OpenAI 兼容 provider 不再需要 "agent 协议" 分支,改为路由到 model-runtime)
- 删掉所有 lca_*.ts(Journal/Artifacts/ChatRow/Persist/Error/Consumer_resilience/RunDriver)
- `lca_run_driver` patch 缩减为: 模型目录注册 + 调流入口替换(~30 LOC)

### D3. 后端实现: 一个 plugin + 一个已有 route

新 plugin: `lca/plugins/providers/openai_stream_encoder/__init__.py`

职责: 把 Agent 内部事件流(`record()` 输出)映射为 OpenAI chunk。**单方向、单工**,无 fan-in。

```python
record(event) →
  ReasoningDelta      → chunk.delta.reasoning_content   # token-level
  ReasoningCompleted  → 不发 chunk(由 handler 自己 mark thinking duration)
  StepTextDelta       → chunk.delta.content             # token-level
  ToolStarted         → chunk.delta.tool_calls[i].{id, name, args}  # 流式
  ToolInvoked         → 完整 tool_calls 段 + 后续 chunk.delta.content 段(markdown 化的产物/输出文本)
  ToolDenied          → chunk.delta.content 写一行 "tool denied: ..."
  AgentRunFinished    → chunk.finish_reason = "stop" + data: [DONE]
```

接入: 挂在 `gateway/openai_shim.py` 已有 `/v1/chat/completions` 路由的 stream 分支上。当 `model ∈ {solo, team, auto}` 且 `stream=true` 时启用 Agent Loop + 该 encoder,其它 model 仍走 non-agent 的 OpenAI 直转;待 LobeHub 接入新 provider 后,**下一阶段**再裁剪 fallback 模型覆盖范围。

### D4. `/runs`、`/runs/{id}/live`、`/runs/{id}` 路由语义清理

- `/runs`、`/runs/{id}`、`/runs/{id}/cancel`、`/runs/{id}/answer`、`/runs/{id}/profile` —— **保留**(一次对话的状态端点)
- `/runs/{id}/live` —— **删除**(原三通道 SSE 由 `/v1/chat/completions` 取代;LobeHub 不再需要)
- `/runs/{id}/doctor`、`/runs/{id}/evidence/{ref}` —— **保留**(只诊断 / 产物)
- `/journal/live` —— 早已 503(`legacy_process_journal_unavailable`),保留 503 即可

**`/runs/{id}/live` 删除意味着前端 patch 一并去掉这一行 fetch**:`fetch('/runs/${runId}/live', ...)`,直接 `fetch('/v1/chat/completions', {method:'POST', body})`。

### D5. 持久化与回放(jsonl/OTel/CLI/doctor)保留

- 内部 `record()` 仍写 jsonl (经 `JsonlJournalProjector`)
- OTel(若有 Langfuse 凭据)仍投射
- `/runs/{id}/doctor` 取 Session Spine projection + jsonl seq,与现在等价
- CLI 与测试消费者:**不需要新加**;他们直接消费 jsonl path;`consumer_contract.py` Protocol 在没消费者的情况下不入 Provider 注册(`registry.ts_consumer_sdk_gen` 也退入 ADR)

### D6. 插件化保留与扩

- `Brain`、`Reasoner`、`Critic`、`SafeExecutor`、`Tool`、`Sandbox`、`Memory`、`Plugin Manifest` —— **不动**
- `Sensor`/`Reducer`/Journal CSS —— **不动**
- 新增 `ChatCompletionStreamEncoder` 是新 plugin,但作用域限于 wire 适配层
- Profile YAML 不变;`profile/web-standard.yaml` 不需要加 `chat_completion_encoder` 提示,因为默认 agent loop 天然让 `/v1/chat/completions` 进入 Agent 路径(选 `model: solo` 即触发)

### D7. 不增加的事

- 不增加 EventSource(maxRetry/backoff)——浏览器原生 fetch + 中断/abort signal 就够
- 不增加 projection channel 续传——结束时一次性 snapshot 给 UI 即可
- 不增加 evidence store 后备——文本直接 inline
- 不增加 SDK 自动生成——`docs/specs/2026-08-29-runs-live-openai-stream-design.md` 是双方 SSOT,前端 TS 与后端 Python 各读一次手写
- 不增加 `projection_seq` 与 `event_seq` 双轴——共用一个 SSE stream 上的 `id:`

## 4. 具体删除清单

### Backend
- `lca/harness/session/live_bus.py` (M2)
- `lca/harness/session/llm_stream_tap.py` (M1)
- `lca/harness/session/scope_recorder.py` (M5.5)
- `lca/harness/session/store.py` 的 projection-only 部分(M2/M3 helper)
- `lca/contracts/harness/events.py` 5 类 delta 扩段(M1)
- `gateway/runs/session_adapter.py` 三通道 `stream_live` / `deltas_pump` / `projection_pump`(M3)
- `lca/plugins/providers/journal_consumer/`(MVA-4)——无消费者可退
- `lca/harness/sdk/ts_consumer_gen.py`(MVA-4)
- `lca/harness/sdk/__init__.py` 中的生成器入口

### Frontend (LobeHub patches)
- `deploy/lobehub/patches/runtime/lcaJournal.ts`
- `deploy/lobehub/patches/runtime/lcaChatRow.ts`
- `deploy/lobehub/patches/runtime/lcaPersist.ts`
- `deploy/lobehub/patches/runtime/lcaError.ts`
- `deploy/lobehub/patches/runtime/lcaArtifacts.ts`
- `deploy/lobehub/patches/runtime/LcaRunDriver.ts`
- `deploy/lobehub/patches/runtime/consumer_resilience.ts`
- `deploy/lobehub/patches/runtime/.generated/lcaJournal.generated.ts`

### Tests
- `tests/harness/test_llm_stream_tap.py`
- `tests/harness/test_session_live_bus.py`
- `tests/gateway/test_session_run_adapter_stream_live.py`
- `tests/test_persistence_regression` 中 session spine 端到端的 wire 部分

### Docs / ADRs
- `docs/adr/0098-session-spine-deltas.md`(改为一份"Rationale:为何放弃 ADR-0098"的回归说明)
- `docs/adr/0097-event-identity-derivation.md`(退并入 ADR-0096 §11,只保留 ULID 生成在 Store 里)
- ADR-0096 §13 Deferred 第 M1-M5.5 段全部 ack 为 superseded

## 5. 保留的旧 wire 兼容性窗口

- **不提供**:旧 `/runs/{id}/live` 任何事件名;旧版不再兼容
- 升级指南: `run-live.md` §"SSE" 整段重写为新规范
- 旧版本 LobeHub 已经 serve-side 自建 journal,无副作用

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| `delta.tool_calls` 触发 LobeHub 工具重放 | 请求体 `tools: []` 不携带 LobeHub 侧工具清单;后端把 `tool_choice: 'none'` 注入,仅 emit 给前端"展示态" `tool_calls` 块(只 render 不可执行);LobeHub 对 `tool_calls` + 自带 role=tool 的回灌在 openai 兼容路径被 runtime 视为展示态(参考 `clientMessageSelect` 现有逻辑)。 |
| Tool message 卡片渲染 | D3 中 plugin emit 完整 `delta.tool_calls` + 后续 markdown 化的产物,等价于 LobeHub 原生 tool 卡片视觉。 |
| 断线续传 | OpenAI chat completion SSE 原生 idless,后端 close 后客户端重发整段 `messages[]` 即可;新对话 session 由 LobeHub 显式发起,不需 `Last-Event-ID`。 |
| 内容过大 token 卡 SSE → 414 | LobeHub 已有 OpenAI client 自动 retry;backend 把 tool result 切分到 chunk 级发送。 |
| Reasoning content 不在所有 provider 默认返回 | Brain 内部聚合 `ReasoningDelta/ReasoningCompleted`,plugin 不依赖具体 LLM。 |

## 7. 验收

```bash
./scripts/lca-ops status          # 看 kernel_serve 是否 healthy
./scripts/lca-ops heal            # 若 kernel 没起,heal 会自动拉起

# 端到端 smoke test
curl -N -H "Authorization: Bearer lca-local" \
  -H "Content-Type: application/json" \
  -d '{"model":"solo","messages":[{"role":"user","content":"hello"}],"stream":true}' \
  localhost:8765/v1/chat/completions

# 期望: 收到标准的 OpenAI chunk 流,done=stop 后流结束
# 然后:浏览器打开 LobeHub,solo 标签,sent 一个 prompt
# 期望: 文本 token 实时显示,reasoning 折叠显示,tool 卡片可点击查看 content
```

- `tests/integration/test_chat_completion_sse.py`(新):断言 chunk 字段
- `tests/integration/test_routes_clean.py`(新):`/runs/{id}/live` 删除 + `/v1/chat/completions` 工作
- 全量回归: `uv run pytest -m 'not real_llm'`

## 8. 实施顺序(rebase-friendly commits)

1. `feat(openai-stream): ChatCompletionStreamEncoder plugin + 单工 Bridge`
2. `refactor(openai-shim): solo|team|auto model 走 Agent Loop` (新路径与旧路径并存)
3. `test(e2e): 端到端 OpenAI SSE chunk shape` (新增,证明新路径)
4. `refactor(lobehub-patches): 删 lca* + 注册 OpenAI provider`
5. `chore(gateway): 删除 /runs/{id}/live 路由`
6. `chore(harness-session): 删除 live_bus / llm_stream_tap / scope_recorder`
7. `chore(contracts): 退 5 类 delta 扩段` (events.py)
8. `docs(adr-0099): 记录 cleanup rationale,supersede 0098 / 0097 / 0096 §13`
9. `docs(specs): update run-live.md + lobehub-integration.md 反映新 wire`

每一步保留 commit-by-commit 可独立 revert;整套大概 ~9 commits。
