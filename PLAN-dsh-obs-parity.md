# PLAN: DSH 观察体系全面对齐 — 补齐规划

> **状态**:Wave 0–6 + G1/G5 PR-4 已落地;15 项验收矩阵 13/15 绿(5/11 刻意跳过)。
> **输入**:用户提供的 A–K 模块清单 + 15 条验收矩阵;`DSH-GAP-AUDIT.md`(G1–G15)、
> `OBS-CONVERGENCE-NEXT.md`、ADR-0183/0184/0185/0186/0188、
> `docs/specs/session-event-pipeline-spec.md`。
> **基线提交**:`4ded684c` + 工作区在途变更(`*.session.jsonl` 镜像退役,
> `spine.jsonl` 为唯一 durable 流)。
> **关系**:本计划是 DSH-GAP-AUDIT 的「数据面补全篇」——审计篇管收敛残留,
> 本篇管 DSH 观察能力中 LCA 尚未具备的模块。**不新建 `dsh_obs` 平行包**;
> 全部差距映射到既有 Session / EventBus / fold 缝上扩展(AGENTS.md §1 Q5)。

---

## 0. 七问速答(AGENTS.md §1)

1. **问题**:LCA 要声称「观察/观测/日志/事件」全面,需对照 DSH 的两条总线
   (Session.append 持久链 + Cordis 实时拦截链)与派生面补齐缺口。
2. **受影响契约**:`SessionEvent` 信封(加 `ignorable`)、Session 词表
   (新增 `feedback/record` 等)、`SessionProtocol`(fork / derive_messages)、
   新观察面 seam(计量 Protocol)。
3. **唯一真值**:in-process = `Session.append` 日志;durable = `<run_id>.spine.jsonl`
   (ADR-0183 I-FW-SSOT-1 / ADR-0186)。其余全是投影。
4. **改变边界**:只扩观察面(记录/派生);不触控制面。
5. **现有机制**:ADR-0186 Session + ADR-0183 目录 + ADR-0185 fold 已表达主体;
   本计划只补缺口,不开平行机制。
6. **失败语义**:读路径未知类型 fail-closed;observer 失败 contained;
   计量纯函数无副作用;遥测后端错误不外溢。
7. **验证**:§4 验收矩阵 15 断言逐条落测试;每个 PR 带 delete-when 与命令。

---

## 1. 现状总盘(已核实,2026-09-05)

`f8b7f089 feat(session)` 已按 DSH 形态落地四家族模块。A–K 清单大部分有锚点:

| 层 | LCA 锚点 | 判定 |
|---|---|---|
| A 信封 | `lca.contracts.harness.tasks.session.SessionEvent`(type/seq/time/data/actor/visibility,全仓唯一信封) | ✅ 基本齐 |
| A 词表 | `lca/contracts/harness/memory/events.py` 25 种 `@session_event` + spine.yaml 101 category | ⚠️ 缺 `ignorable` 与读端校验 |
| B 存储/append | `lca/plugins/session/runtime/{session,store}.py`(单调 seq、深冻、拒重入、observer、flush listener) | ✅ 基本齐 |
| B surface | `lca_kernel/events/fold.py::foldSurface`(3 种表面类型映射到 `spine.llm.request.header` / `.assistant` / `spine.body.tool.execute.end`,replace 带 provenance) | ⚠️ 离线 fold 有,Session 内增量 surface 索引与 derive_messages 缺 |
| C 实时总线 | `EventBus` publish/subscribe(ADR-0183)+ vendored Cordis `waterfall`/`serial`(`lca/harness/middleware/registry.py`)+ tool pipeline pre/post + checkpoint 边界 | ⚠️ 能力在,缺 DSH 式命名拦截目录 |
| D 持久化 | write-behind(`lca/infrastructure/persistence/`)+ `SpineFileSink` 经 `Session.observe` 写唯一 `spine.jsonl`;`FsyncProtocol` 三档;`SESSION_FORMAT_VERSION=0` 不匹配拒载 | ⚠️ 读路径缺未知类型拒绝 + 撕裂尾回归 |
| E 投影 | `plugins/session/{projection_registry,projection_cache,session_stats,session_turn_outline}`、step_tree deriver、`AgentStateProjection`、MaterializationStore watermark | ⚠️ 缺 token_usage / context_pressure |
| F 计量 | 仅 `CostProjector`(LlmCallCompleted → cost by pricing_ref) | ❌ 缺启发式/路由计价/影子扣减/usage 锚定 |
| G 遥测 | `plugins/session/{telemetry_capture,telemetry_otel}`:live/on_demand、redactor 注册表、`SharingPolicy(full/feedback_only/disabled)`、OTLP **logs** 后端 | ⚠️ 缺 `feedback/record` 事件与 feedback gate 接线 |
| H 上传水位 | 无 | ⏭️ 刻意跳过(DeepSeek 后端专属) |
| I 查询 | Journal 面:TraceInspector / `lca-ops explain` / webserver trajectory / `journal replay`;Session 面:replay / recovery / resume_point | ⚠️ 缺 fork、transcript 导出、session 级检索 |
| J checkpoint/title | `checkpoint_policy`(模型请求前/工具副作用前/步边界三检查点)+ `session.checkpoint.v1`;`title_service` + `title_llm_provider` + `session.title.v1`(ADR-0188) | ✅ 齐 |
| K 驱动夹具 | `tests/scenarios/test_event_delivery_e2e.py` 等分散 | ⚠️ 缺「全词表逐类型发射 + 逐步不变量断言」的 RecordingLoop |

---

## 2. 对照当前 DSH 代码的清单勘误(先纠正,再排期)

核对 `~/deepseek-harness` 当前代码后,用户清单有 3 处与现状不符,**不应照做**:

| 清单项 | DSH 代码事实 | 处置 |
|---|---|---|
| D `persist.migrate` v0→v1→v2 相邻迁移链 | `format.ts::refuseForeignFormatVersion`:版本 ≠ `SESSION_FORMAT_VERSION` 抛 `SessionFormatUnsupportedError`(“upgrade the harness, never corrupt”);storage 子系统文档:“no migration, pre-release stance” | **删除**。LCA 现状(版本不匹配拒载)已对齐 |
| D `persist.generation` `session.vN.jsonl` | `index.ts:297`:逻辑文件名恒为 `session.jsonl`(物理仅 `.jsonl` / `.jsonl.zstd` 之分) | **删除**。无代际文件机制 |
| A 核心事件含 `assistant/attempt` | `known-event-types.ts`(由 `SessionEventMap` 生成)**无** `assistant/attempt`;失败尝试用量在 `llm/retry` + `llm/retry-started`,流增量是 `assistant/chunk`(落盘、派生时跳过) | **修正**。LCA 对位:`thinking.delta.v1`(流增量)+ `model.failed.v1`(失败)。可补 `llm/retry` 对位词 |

另确认(与清单一致,作验收锚):

- `SurfaceEventType` 恰 3 种:`user/message` / `assistant/message` / `tool/result`
  (`packages/core/session/src/types.ts:373`)。
- 信封字段:`type/seq/time/data` + `ignorable?: true` + `surfaceOp?` + `sourceEventSeqs?`
  (surface 事件必带 `surfaceOp`;replace 节点 `sourceEventSeqs` 必须覆盖被替换源)。
- 读路径对未知且非 `ignorable` 类型 fail-closed(注释明确:“silently skipping a
  required event would reconstruct a wrong session”)。
- 撕裂尾:扫描器保留可恢复前缀,末尾无换行的半行按撕尾忽略,同时检测已提交区
  seq 空洞(`format.ts:394-445`)。
- 遥测共享态:`'full' | 'feedback-only' | 'disabled'`;redaction 走
  `session-telemetry/record` waterfall(LCA 用 redactor 注册表,是有意差异,保留)。
- token-meter 快照:`logRevision / baseline / surfaceDeltaTokens / totalTokens /
  surfaceTokens / nodes[]`(`packages/llm/token-meter/src/types.ts`)。
- 上传水位:`session-log-deepseek/delivery-accepted`(throughSeq 必须指向前序事件,
  有不变量校验)——仅 DeepSeek 回传需要。

---

## 3. 逐层差距与补齐动作

### Wave 0 — 在途工作(引用,不重复排期)

| 项 | 归属 |
|---|---|
| ADR-0186 PR-3a–3h 收敛(Session.append 唯一入口、publisher/deriver/sink 迁移、EventSpine shim) | ADR-0186 §5 |
| DSH-GAP-AUDIT G1/G5(PR-3.1 handler 迁 fold)、G14(ADR-0184 PR-D 接线) | `DSH-GAP-AUDIT.md` §5 |
| `*.session.jsonl` 镜像退役、spine.jsonl 唯一 durable(工作区在途) | 当前未提交变更 |

**本计划所有 PR 排在 Wave 0 之后**(依赖 Session 真值层定型)。

### Wave 1 — 契约地基(★ 验收 6/12 的前提,需 ADR)

| # | 动作 | 触点 | 契约影响 |
|---|---|---|---|
| 1.1 | `SessionEvent` 信封加 `ignorable: bool = False`(落盘字节新增可选字段) | `lca/contracts/harness/tasks/session.py`、kernel 信封、`lca_kernel/events/sinks` 序列化 | Schema 变更 → ADR + 序列化兼容测试;旧记录缺字段按 `False` 读 |
| 1.2 | 读路径已知类型校验:`SpineReader` / restore 打开时校验 `type ∈` 注册目录;未知且非 `ignorable` → 拒绝打开;`ignorable` → 跳过 | `lca_kernel/events/reader.py`、`plugins/session/runtime/recovery.py` | fail-closed 行为新增;需架构测试 |
| 1.3 | 插件类型合并语义:yaml 注册的 category 即「本构建已知集」;外部产生的 `ignorable` 事件允许携带未注册类型存活于日志(只跳过不拒) | `lca_kernel/events/registry.py` known-set 导出 | 对齐 DSH “persisted ignorable marker, not registration” 决策 |
| 1.4 | append 端 schema 运行时校验启用(承接 DSH-GAP-AUDIT G11 / note 4 方向,与 `PLAN-payload-typing.md` 合流) | `EventSpec.fields` 校验骨架 | 不改线格式 |

**验收**:断言 6(脏 log 拒读)、12(插件类型可 merge 可跳过)。

### Wave 2 — Token / 成本计量(★ 整层缺失,纯观察面无 ADR)

DSH `packages/llm/token-meter` 的 Python 对位,按扩展路径落:
`Protocol(lca/contracts/observability/token_meter.py)→ provider → @plugin`。

| # | 动作 | 说明 |
|---|---|---|
| 2.1 | `TokenMeter` Protocol + 快照 DTO(`log_revision/baseline/surface_delta_tokens/total_tokens/surface_tokens/nodes`) | 形状对齐 DSH;命名用 snake |
| 2.2 | 启发式计量器(无 tokenizer 时固定系数)+ `model.completed.v1.usage` 存在时的 **usage 锚定**:仅当请求信封与计量基线一致才复用 provider usage,否则 estimated(验收 9) | 消费 Session 事件 fold,纯函数 |
| 2.3 | 路由计价:按 `spine.llm.request.header` 的 model 字段路由单价(含视觉/多模态单价占位) | 复用 `DefaultCostPricingTable`,CostProjector 保留为 Journal 面成本投影,两者不合并(一个管 surface 压力,一个管账单) |
| 2.4 | `measure(session, header?)` 增量 replay API + 投影注册(`proj.registry` 对位 = `projection_registry`) | 冷读 = 全量 fold 等价(验收 14 附带覆盖) |
| 2.5 | (缓办)compaction/prune 影子扣减:等 LCA 引入 surface 压缩事件词后再落;先预留 `shadowed_token_count` 字段位 | 当前 `semantic_compaction` 是记忆层压缩,与 surface 影子计价不同物 |

**验收**:断言 9;新增计量快照单测(确定性:同一事件流两次计量结果相同)。

### Wave 3 — 遥测闭环(★ 验收 10)

遥测骨架已齐(`telemetry_capture` + `telemetry_otel` OTLP logs 后端),缺的是
**feedback 来源与门控接线**:

| # | 动作 | 契约影响 |
|---|---|---|
| 3.1 | 新增 `feedback/record` 词表项(`@session_event`,visibility=audit;字段:rating/标签/引用 message_seqs) | 词表扩展 → 按 C11 走目录 + ADR/Note 闭环(事件闭集) |
| 3.2 | `FEEDBACK_ONLY` 门控:未见 `feedback/record` 不外送;见到后释放该 session 未释放前缀(游标推进) | `telemetry_capture` 内逻辑 + 测试 |
| 3.3 | 披露面:`lca-ops` 或 webserver 暴露当前 `SharingPolicy` + 后端 dropped/redacted 计数 | 读面,无契约变更 |

**验收**:断言 10(无 feedback 时 sink 为空)。

### Wave 4 — 操作面:fork / derive_messages / transcript(★ 验收 3/4/13)

| # | 动作 | 说明 |
|---|---|---|
| 4.1 | `SessionProtocol.fork(at_seq)`:截断快照开新 Session,header 盖 `parent_session` / `seed_length` / `is_seeded=True`(字段已存在),追加 `session.end_seed.v1` 对位事件标记继承边界 | 新公开操作 → Protocol 变更须同步全部实现(当前仅 1 个实现 + 测试替身) |
| 4.2 | 遥测游标重置:fork 出的 session 从 seed 边界后开始计量,不重复上报祖先历史 | `telemetry_capture` handoff cursor |
| 4.3 | `derive_messages(session)` API:从 surface 节点投影消息序列(对 `foldSurface` 结果的消费层),增量缓存 | 验收 3(≡ 重放对比) |
| 4.4 | `transcript` 导出:仅 surface 的事件序列导出(人眼/对外),复用 4.3 | `lca-ops` 子命令或导出函数 |
| 4.5 | surface 投影进 Session 增量维护(可选,性能项):Session 内维护 surface 节点列表,`foldSurface` 离线语义不变 | 与 4.3 同批评审 |

**验收**:断言 3、4、13;fork 后 `derive_messages` 与全量重放一致。

### Wave 5 — 查询面补齐(可选增强,非「全面」的必要条件)

| # | 动作 | 现状对位 |
|---|---|---|
| 5.1 | tool call↔result 对齐查询(时长/ok/error)按 `invocation_id` | Journal 面已有(`TraceInspector`),Session 面经 `spine.body.tool.execute.*` 补一个折叠查询 |
| 5.2 | 按 type/turn/step 过滤的 session 事件查询 | `SpineReader` + 过滤函数;`lca-ops` 已有 `journal trace`,补 session 面入口 |
| 5.3 | (缓办)corpus 检索(DSH `session-query` 全文检索) | 产品需求未出现前不做 |

### Wave 6 — RecordingLoop 夹具(★ 验收矩阵的执行器)

| # | 动作 | 说明 |
|---|---|---|
| 6.1 | `tests/scenarios/` 新增 RecordingLoop:按 spec §5 时序发射全部已注册类型各一条(`turn.started → step.started → message.accepted → model.requested(+request.header)→ assistant.responded → tool 执行 → step.ended → turn.ended`,加 audit 族) | 不执行真实工具;fake LLM |
| 6.2 | 每步后跑不变量断言:seq 连续、turn/step 嵌套、模型请求内容 ⊆ 日志可重建(对 `foldRequestHeader` / surface fold 断言) | 对齐 DSH `invariant.ts` 关系不变量 + 验收 13 |
| 6.3 | 撕尾/脏类型/未知类型三个破坏性用例直接复用该夹具产物 | 验收 6、7 |

---

## 4. 验收矩阵(用户 15 断言 → 现状与落点)

| # | 断言 | 现状 | 落点 |
|---|---|---|---|
| 1 | 只有 `append` 产生持久事件 | ✅ `tests/architecture/test_session_ssot_invariants.py`(I-SESSION-1/3)+ import-linter business-event-isolation | 保持,随 Wave 0 收口 |
| 2 | surface 仅 3 种 | ✅ `fold.py::SURFACE_EVENT_TYPES` + `test_fold_surface.py` | 已绿 |
| 3 | `deriveMessages()` ≡ 重放 surface | ✅ `messages.py` + `test_messages_and_fork.py` | Wave 4 ✅ |
| 4 | replace 不删历史事件 | ✅ `foldSurface` 语义(events 保留、surface 变短)+ `test_fold_surface.py` | 已绿,RecordingLoop 复断 |
| 5 | prune 紧跟影子计价 | ⏭️ LCA 无 surface 压缩词表 | Wave 2.5 预留;引入压缩词表时补(需事件闭集 ADR) |
| 6 | 未知非 ignorable → 拒读 | ✅ `log_reader` + `restore_from_log` + 脏 log 测试 | Wave 1 ✅ |
| 7 | 撕尾不暴露 | ✅ `test_torn_tail_read.py` + `restore_from_log` | Wave 6 ✅ |
| 8 | waterfall 不 next 即中断 | ✅ middleware/hook 族测试(`test_think_guard_consumer.py` 等) | 已绿 |
| 9 | usage 仅信封一致时当锚 | ✅ `HeuristicTokenMeter` + `test_token_usage.py` | Wave 2 ✅ |
| 10 | FEEDBACK_ONLY 无 feedback 不外送 | ✅ `telemetry_capture` gate + 测试 | Wave 3 ✅ |
| 11 | 上传失败不写水位 | ⏭️ 不适用(无 DeepSeek 回传) | 跳过 |
| 12 | 插件类型可 merge 可跳过 | ✅ `ignorable` + event_catalog fail-closed | Wave 1 ✅ |
| 13 | 模型请求内容 ⊆ 日志可重建 | ✅ request.header + RecordingLoop catalog 参数化 | Wave 6 ✅ |
| 14 | 投影冷读 = 全量 fold | ✅ `test_token_usage.py` 冷热对比 | Wave 2 ✅ |
| 15 | OTEL turn/step/tool 树确定性再生 | ✅ `test_otel_live_replay_parity.py` | Wave 6 ✅ |

---

## 5. 排序与依赖(建议两周验完的骨架)

```
Wave 0(在途)──────────────────────┐
                                   ▼
Wave 1 契约地基(ADR)──► Wave 6 夹具 ──► 验收 6/7/12/13
        │
        ├─► Wave 2 计量 ──────────────► 验收 9/14
        ├─► Wave 3 遥测门控 ──────────► 验收 10
        └─► Wave 4 fork/derive ───────► 验收 3/4
Wave 5 查询增强(机动插入,不阻塞)
```

每个 Wave 内各 # 独立可 revert;跨 Wave 依赖只有「Wave 0 → 其余」。

## 6. 需要先行 ADR / Note 的变更(按 AGENTS.md §1 闸门)

| 变更 | 原因 | 形式 |
|---|---|---|
| `ignorable` 入信封 + 读路径 fail-closed(Wave 1) | 信封字节 + 读语义契约变更 | ADR(延伸 ADR-0186)+ 序列化兼容测试 |
| `feedback/record` 等新词表(Wave 3) | C11 事件闭集 | ADR/Note + catalog + 消费方闭环 |
| `SessionProtocol.fork` + `session.end_seed.v1`(Wave 4) | 生命周期新状态转移(新 session 的 lineage/计量边界) | ADR(延伸 ADR-0186/0187 域) |
| TokenMeter seam(Wave 2) | 新公共接口,走 Protocol/DTO 先行 | 不需 ADR(纯观察面投影),走扩展路径 |

## 7. 刻意不做(与用户清单 §4 一致,再加本地决策)

- 上传水位 / DeepSeek 回传(§H):无对应后端;ADR-0184 managed-delivery 已覆盖
  「投递生命周期」本地语义。
- `session.vN.jsonl` 代际与迁移链:DSH 当前代码亦无(§2 勘误)。
- 模型适配器、真实工具执行、system-prompt 组装、Web UI:agent 产品域。
- 词表改名为 DSH 斜杠风格:语义对齐即可,命名归本仓命名规范。
- `todo/write` 词表与投影:本仓无 todo 概念;需要时随产品能力一起引入。

## 8. 验证入口汇总

```sh
# 现状基线(写码前先跑,区分既有失败)
uv run pytest tests/architecture/test_session_ssot_invariants.py tests/lca_kernel/events/test_fold_surface.py -q
./scripts/lca-ops notes-check

# Wave 交付后新增(示意)
uv run pytest tests/scenarios/test_recording_loop.py \
  tests/observability/session/test_known_types_fail_closed.py \
  tests/observability/session/test_torn_tail_read.py \
  tests/observability/token_meter/ tests/plugins/session/test_telemetry_feedback_gate.py -q
```
