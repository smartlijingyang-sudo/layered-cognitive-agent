# ADR-0096: Journal Protocol Layer 一切插件化 — 协议 SSOT 双向落地 + 链路日志清晰

## 状态

**Accepted（含 §13 两阶段拆分修订）— 2026-08-28。** 本文继承 ADR-0037 / ADR-0063 / ADR-0066~0069 / ADR-0074 / ADR-0082 / ADR-0084 / ADR-0085 全部约束，并把它们落到的协议层做一次**第一性原理重塑**。当前问题不在某个 bug，而在：**协议升级路径无 SSOT 双向落地、协议演化无契约测试守门、协议消费跨仓无统一机制**。

> **2026-08-28 修订要点**：12 PR 实施序列拆为 **Phase 1 MVA（4 PR，1-2 周完成）** 与 **Phase 2 Deferred（8 PR，按需启动）**。详见 §13。

> **核心决策：把 envelope schema、event identity、visibility policy、transport、consumer contract、manifest derivation 全部下沉为独立的协议层 seam + provider，按 cordis capability 接入；任何 envelope 变更必须同时在三处落地（schema 模块 + 双向契约 fixture + profile 装配），由 ADR 程序强制。**

---

## 0. 读取顺序

本文自包含，但要落地前请按下列顺序读：

1. §1 问题陈述（含 21 条根因机制）— 了解为什么打补丁无效
2. §2 第一性原理 + 不可变约束 I1~I8 — 知道底线
3. §3 目标架构 + 七层 seam — 知道整体形态
4. §4 模块边界与依赖图 — 知道职责切分
5. §5 链路日志清晰度契约 — 知道每帧必带什么
6. §6 实施序列（PR-0~PR-12）— 知道动手顺序
7. §7 验收规约 — 知道"完成"如何被判定

---

## 1. 问题陈述

### 1.1 用户可观察症状

2026-08-28 用户从浏览器 `http://10.36.6.252:3010` 发起一次 LobeHub 对话（run_302c22421883）：

| 期望 | 实际 |
|---|---|
| 流式显示模型回答"你好！我是你的 AI 助手…" | **完全看不到** |
| 实时显示 reasoning | **完全看不到** |
| 后端 log 看到 207 个事件流过 | ✅ 看到 |
| `curl http://127.0.0.1:8765/runs/<id>/live` 看到 207 帧 SSE | ✅ 看到 |
| `curl http://127.0.0.1:3010/lca-api/runs/<id>/live` 看到 207 帧 SSE | ✅ 看到 |
| 前端 fetch `/lca-api/runs/<id>/live` 收到 207 帧并渲染 | ❌ **静默渲染为空文本** |

**问题在跨仓协议漂移：journal envelope 已经从 v1（`{event: {typed payload}}`）迁移到 v2（`{data: {typed payload}, descriptor, event_id, scope}`），后端完全切到 v2，前端 `parseSseBlock` 仍假设 v1。**所有 StepTextDelta 帧的 `text_delta` 被解析为 `undefined`，所有 ReasoningDelta 帧的 `text_delta` 同样为 `undefined`。

### 1.2 为什么"修一个 bug"无效

只改 `parseSseBlock` 让它读 `data.data` 看似修好，但本质问题是**协议升级路径没有 SSOT 双向落地机制**：

- 后端 ADR-0065 §四 升级 envelope，没同步通知 lobehub-ui 仓
- 没有 golden fixture 让 CI 拦截 envelope 漂移
- 没有 consumer contract seam 把"前端如何读 envelope"做成一等公民
- 没有契约测试保证 schema 与 projection 一致

下次升级又会发生同样的事——而且如果更隐蔽（如某个新事件类型不被前端识别），连症状都不会被报告。

### 1.3 系统性根因盘点（21 条机制级问题，按架构层次排列）

| 机制 | 现象 | 根因 | 架构层 |
|---|---|---|---|
| **A** | 前端解析 v2 envelope 拿空文本 | 协议跨仓漂移，无契约测试 | SSOT 缺失 |
| **B** | 后端 envelope 升级前端不感知 | 协议消费契约没在 SSOT 落地 | SSOT 缺失 |
| **C** | `RuntimeObserved plugin.inventory` 进生产 SSE，119 项插件清单撑爆单帧 | `is_sse_visible` 写了不调用 | Visibility Policy 未实施 |
| **D** | `event_id` 在内存 StampedEvent 是空字符串，磁盘 envelope 是 hash 派生值 | `RunStore.append` 不闭环填 event_id | Event Identity 未插件化 |
| **E** | `RunManifest.terminal_event_id = ""` 被多次写入但 `terminalizer` 短路文件 fallback | 上述 D 的下游；derived view 持硬字段违原则 | Manifest Schema 越权 |
| **F** | `_derive_event_id` 用 float `ts` → replay 不稳定 | 派生函数不稳 | Event Identity 未插件化 |
| **G** | 顶层 `lca_journal.jsonl` v1 与 per-run `journal.jsonl` v2 双轨并存 | migrate 没推进 | Ledger 单源原则被破坏 |
| **H** | `agent_role` 字段三处分散（scope.agent_role / data.agent_role / attributes.actor_role），前端直接拿 ID 当 speaker | 身份身份身份未规范化 | Identity Schema 不收敛 |
| **I** | `default → ignore` 静默吞帧（DecisionMade / AgentRunStarted / ContextManifested 都被 ignore） | 未识别帧无 metric | Consumer 契约缺 metric |
| **J** | StepTextDelta `channel=decision` 文本被静默过滤 | 宪法 C2 双平面被误读成 UI 隐藏借口 | 双平面语义在 UI 层 |
| **K** | `readSse` 缓冲累积无上限 | 缺 max buf + frame budget | Transport 韧性 |
| **L** | LcaRunDriver 重连硬编码 400ms 无退避无 dedup 无 max retry | 缺 reconnect 健壮性策略 | Consumer 韧性 |
| **M** | `iter_live_sse(tail, after_seq, redact=False)` 在 live 路径违反 redact 默认契约 | transport 默认值不一致 | Transport 契约 |
| **N** | `_TEXT_CHANNEL_ALL` 推所有 channel，前端过滤 | 数据发了不用是浪费 | Transport 过滤 |
| **O** | `data.seq` 字段名残留（v1 用 seq，v2 用 run_seq） | 字段名迁移不彻底 | Schema 命名一致性 |
| **P** | `Last-Event-ID` 只支持整数 seq，未来切 event_id 会丢帧 | 协议升级路径缺演进测试 | Consumer 契约 |
| **Q** | 重连 dedup 缺 `seen_seq` set | consumer 韧性问题 | Consumer 韧性 |
| **R** | `RuntimeObserved plugin.inventory` 该写 profile snapshot 而非 journal | journal 与 snapshot 边界混淆 | 写入责任 |
| **S** | `_log.debug("terminal_event_id_from_hub_failed", ...)` 报 debug 级别 | invariant 违反该 warning | 错误级别 |
| **T** | RunManifest 字段非空无 runtime guard | ADT 不闭合 | Manifest Schema |
| **U** | `data.data` 字段名嵌套歧义（前端看到 `data.data.text_delta`） | 字段命名不语义化 | Schema 命名 |

**根因不是 21 个 bug，是 1 个架构缺陷：协议层不是 seam。** 所有 21 条都源于 envelope schema / identity / visibility / transport / consumer 五件事没有走 capability 路径，无法在 profile 层声明+替换+验证。

### 1.4 为什么不在旧机制上打补丁

| 提案 | 评估 |
|---|---|
| 在 `parseSseBlock` 加 v2 优先逻辑 | ❌ 治标，下次升级又发生 |
| 在 `_terminal_event_id_for` 加 file fallback 容错 | ❌ 治标，根因是 memory/磁盘 event_id 不一致 |
| 给 `is_sse_visible` 加 audience 过滤 | ❌ 单独过滤不够，需要 plugin 注册 |
| 给 plugin.inventory 加 frame size 截断 | ❌ 该事件不该进 SSE |
| 把 `terminal_event_id` 改成 `_terminal_event_seq` | ❌ 单字段改造，根因是 derived view 持硬字段 |
| 给 LcaRunDriver 加 setTimeout 退避 | ❌ 单点韧性，根因是 transport 缺契约层 |

**所有"打补丁"提案都把根因留着，把症状盖住。** 本 ADR 不打补丁。

---

## 2. 第一性原理与不可变约束

### 2.1 第一性原理

```
协议 SSOT 双向落地 = schema 模块（后端 dataclass/Pydantic）
                   + 契约 fixture（golden jsonl + projection expected）
                   + consumer seam（前端解析走 capability 注册）
                   + profile 装配（profile.yaml 声明哪些 transport/consumer 启用）
                   + ADR 流程（任何 envelope 改动必走 §6 实施序列）
```

```
链路日志清晰度 = trace_id + plan_ref + event_id + schema_version
                四键在每个 transformation 阶段都不丢
                跨仓（lca → lobehub）通过 envelope 携带
                任一端可发起 trace 重建
```

```
一切插件化（继承 ADR-0085）= seam 声明注册中心
                         + provider 注入实现
                         + profile 选择具体组合
                         + 替换实现时改 profile，不改相邻代码
```

### 2.2 不可变约束

| 编号 | 约束 | 继承 / 新增 |
|---|---|---|
| **I1** | Journal 单一事实源（每 run 一个 append-only ledger） | 继承 ADR-0063 I1 |
| **I2** | Schema 升级必走 SSOT 双向落地 | **新增** |
| **I3** | Event identity 由构造时闭环派生，**不再用 float ts** | **新增**（根因机制 D/F） |
| **I4** | Visibility policy 是 seam，按 audience + domain 决定事件能否到达 transport / consumer | **新增**（根因机制 C） |
| **I5** | Transport 帧 size 有 budget，超出拒推并告警；不在 producer 截断、不在 consumer 默默吞 | **新增**（根因机制 C/K） |
| **I6** | Consumer contract 是 seam，前端投影函数以 capability 注册，可单独测试 | **新增**（根因机制 A/B/I） |
| **I7** | Derived view（RunManifest / TraceReport）不持 hard id；只持 `run_seq` 等 journal 主键 | **新增**（根因机制 E） |
| **I8** | 双平面 channel（decision / answer）在 UI 区分显示，不静默丢弃 | **新增**（根因机制 J） |
| **I9** | Consumer 韧性（backoff / dedup / max_retry）是 consumer seam 内部属性 | **新增**（根因机制 L/Q） |
| **I10** | 写入边界错配事件（plugin.inventory 等静态元数据）写 profile snapshot，不入 journal | **新增**（根因机制 R） |
| **I11** | schema 字段命名语义化（`payload` 优于 `data.data` 嵌套） | **新增**（根因机制 U） |
| **I12** | 协议升级必触发 ADR 程序（任何 envelope / identity / visibility 字段变更必须新 ADR 或本 ADR 修订） | **新增**（根因机制 A） |

> **核心约束 I2 + I12 是整个 ADR 的关键**：协议升级不是"改 dataclass + 改前端"的二步动作，而是"改 schema + 改契约 fixture + 改 consumer seam + 改 profile 装配 + 改 ADR"的多步动作，由 CI 与 §6 实施序列强制。

---

## 3. 目标架构：七层 seam + 一条链路日志

### 3.1 七层 seam 总览

```
┌──────────────────────────────────────────────────────────────────┐
│ L7: Manifest Derivation（derived view）                          │
│   seam: manifest_derivers   provider: manifest-derive-run        │
│   - RunManifest 收敛到 run_seq 主键                             │
├──────────────────────────────────────────────────────────────────┤
│ L6: Consumer Contract（消费契约）                                │
│   seam: journal_consumer_contracts                              │
│   providers:                                                   │
│     - consumer-lobehub (frontend projection)                   │
│     - consumer-cli (ops/replay)                                │
│     - consumer-coding-agent (tool wrapper)                      │
│   - 韧性策略：backoff / dedup / max_retry 都在 provider 内部   │
├──────────────────────────────────────────────────────────────────┤
│ L5: Transport（传输）                                            │
│   seam: journal_transports                                      │
│   providers:                                                   │
│     - transport-sse (live SSE)                                 │
│     - transport-jsonl (disk)                                   │
│     - transport-otel (external telemetry)                      │
│   - frame size budget：单帧 > 16KB 拒推 + 告警                │
│   - redact 默认 True（live UI），ops 模式显式 False             │
├──────────────────────────────────────────────────────────────────┤
│ L4: Visibility Policy（可见性策略）                              │
│   seam: journal_visibility_policies                             │
│   providers:                                                   │
│     - visibility-audience-domain（默认 policy）                │
│     - visibility-strict（ops 全开）                            │
│     - visibility-restricted-only（外部 telemetry）             │
├──────────────────────────────────────────────────────────────────┤
│ L3: Event Identity（事件身份）                                    │
│   seam: event_identities                                        │
│   providers:                                                   │
│     - identity-stable-hash（默认，sha256(run_id, seq, type))  │
│     - identity-uuid（可选，UUIDv7）                            │
│   - 构造时闭环派生，**不接 float ts**                          │
├──────────────────────────────────────────────────────────────────┤
│ L2: Envelope Schema（封套模式）                                  │
│   seam: journal_schemas                                         │
│   providers:                                                   │
│     - schema-v2（当前 default）                                │
│     - schema-v3（未来迁移目标）                                │
│   - Versioned, semver, 带 migration table                      │
├──────────────────────────────────────────────────────────────────┤
│ L1: Journal Core（账本核心）                                     │
│   - StampedEvent 单一来源                                      │
│   - RunStore.append 单一入口                                   │
│   - EventDescriptor 单一治理查询面                              │
│   继承 ADR-0063，本 ADR 不动                                    │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 链路日志清晰度：四键契约

每一次 transformation 都必须保留并透传四键：

```
trace_id     跨 run 关联骨架
plan_ref     编译后运行计划哈希（PR-6 V5）
event_id     事件全局唯一 id（identity-stable-hash 派生）
schema_version  envelope schema 版本（"v2.3.0"）
```

| 阶段 | 输入四键 | 输出四键 | 校验 |
|---|---|---|---|
| L1 journal append | run_scope {trace_id, plan_ref} + seq | stamped.event_id + 四键 | append 后 stamped 必须带齐 |
| L3 identity 派生 | (run_id, seq, event_type) → event_id | stamped.event_id | 不接 ts |
| L4 visibility 评估 | stamped + audience + domain | 允许/拒绝 + 原因 | 拒绝时记日志但不写 SSE |
| L5 transport 序列化 | stamped + schema_version | SSE 帧 / JSONL 行 / OTel span | 单帧 ≤ 16KB |
| L6 consumer 投影 | SSE 帧 + consumer contract | Projected 对象 | 校验 contract schema |
| L7 manifest 派生 | journal + run_seq watermark | RunManifest | 只持 run_seq，不持 event_id 字符串 |

跨仓透传：lca → lobehub 的 SSE 帧 envelope 顶层必须包含四键（已经包含 trace_id / plan_ref / event_id；新增 schema_version）。

---

## 4. 模块边界与依赖图

### 4.1 模块列表（七层 + 一组契约工具）

| 模块 | 路径 | 职责 |
|---|---|---|
| **journal-schemas** | `lca/contracts/observability/schemas/` | Versioned envelope Pydantic schema + migration table |
| **event-identities** | `lca/plugins/seam_definitions/event_identity.py` | seam 声明 |
| **identity-stable-hash** | `lca/plugins/providers/event_identity/stable_hash.py` | sha256(run_id, seq, type) 派生 |
| **journal-visibility** | `lca/plugins/seam_definitions/journal_visibility.py` | seam 声明 |
| **visibility-audience-domain** | `lca/plugins/providers/journal_visibility/audience_domain.py` | 默认 policy |
| **journal-transports** | `lca/plugins/seam_definitions/journal_transport.py` | seam 声明 |
| **transport-sse** | `lca/plugins/providers/journal_transport/sse.py` | SSE 序列化 + 帧 budget |
| **transport-jsonl** | `lca/plugins/providers/journal_transport/jsonl.py` | 磁盘落盘 |
| **journal-consumer-contracts** | `lca/plugins/seam_definitions/journal_consumer.py` | seam 声明 |
| **consumer-lobehub** | `lca/plugins/providers/journal_consumer/lobehub/` | TypeScript projection via generated SDK |
| **consumer-cli** | `lca/plugins/providers/journal_consumer/cli/` | CLI 投影 |
| **manifest-derive-run** | `lca/plugins/seam_definitions/manifest_derivers.py` | RunManifest 派生 |
| **profile-snapshot** | `lca/plugins/seam_definitions/profile_snapshot.py` | 静态元数据快照（替代 journal 中的 plugin.inventory） |
| **contract-test-fixtures** | `tests/fixtures/journal_v2_golden/` | Golden SSE 流 + projection 期望 |

### 4.2 依赖图

```
L1 journal-core (existing, unchanged)
   ↑
L2 journal-schemas (depends on L1 contracts)
   ↑
L3 event-identities (depends on L2 schema)
   ↑
L4 journal-visibility (depends on L2 schema + L3 identity)
   ↑
L5 journal-transports (depends on L2 + L3 + L4)
   ↑                     ↓ (cross-cutting)
L6 consumer-contracts   contract-test-fixtures
   ↑
L7 manifest-derivers (depends on L1 + L3 + L6)
```

### 4.3 责任边界（绝不越界）

| 层 | 责任 | 不做 |
|---|---|---|
| L1 journal-core | append-only ledger, 验证, 策略, 盖章 | 不做序列化、不做 identity 派生、不做 transport |
| L2 schemas | 声明 envelope 形状 + 迁移表 | 不做 visibility、不做 transport 调度 |
| L3 identity | 派生 event_id | 不决定是否落盘、不决定 audience |
| L4 visibility | 决定某事件能否到某 channel | 不序列化、不投影 |
| L5 transport | 序列化到字节流 + 帧 budget + redact | 不投影到领域对象 |
| L6 consumer | 字节流 → 投影对象 | 不持久化、不派生 manifest |
| L7 manifest | journal 主键 → RunManifest | 不存硬 event_id 字符串、不持久化 |

---

## 5. 链路日志清晰度契约

### 5.1 envelope 四键强制

```python
# journal-schemas/v2.py
class EnvelopeV2(BaseModel):
    schema_version: Literal["v2.0.0"]  # 新增
    event_id: str                      # 构造时由 L3 派生
    trace_id: str
    run_id: str
    run_seq: int                       # 主键
    plan_ref: str = ""                 # 来自 ContextVar
    occurred_at: float
    descriptor: EventDescriptor
    payload: dict[str, Any]            # 改名 data → payload，根除机制 U
    scope: RunScope
    causation: Causation
    evidence: list[EvidenceRef] = []
```

迁移：v1 `{event: {...}}` / v2 `{data: {...}}` → v2.0.0 `{payload: {...}, schema_version: "v2.0.0"}`。
migrate 表记录每个 envelope 字段的演进路径；lca-journal-migrate 工具执行。

### 5.2 trace 重建四向

四个入口可独立重建同一 trace：

| 入口 | 输入 | 输出 |
|---|---|---|
| 后端 replay | run_id | JSONL 重放 → StampedEvent 序列 |
| 前端 SSE | last_event_id（run_seq） | 流式 envelope |
| Ops CLI | trace_id 或 run_id | Mermaid 图 + 文本报告 |
| Coding Agent tool | run_id + focus | 结构化 JSON |

任一入口失败可降级到另一入口（日志里记"原计划从 X 走，降级到 Y"）。

### 5.3 日志结构

每个 transformation 记一条结构化日志：

```python
_log.info(
    "journal_transformation",
    stage="visibility_evaluate" | "transport_serialize" | "consumer_project" | "manifest_derive",
    run_id=...,
    trace_id=...,
    plan_ref=...,
    event_id=...,
    schema_version="v2.0.0",
    decision="allow" | "reject" | "truncate" | "drop",
    reason=...,
)
```

四键 + decision + reason 是 invariant：缺一即为日志 bug。

---

## 6. 实施序列（12 PR · MVA 拆分见 §13）

> **本节是落地中央账本；任何 PR 完成时同步更新本节"已落地"列。**
> **重要**：§6 是 12 PR 的完整视图；落地时按 §13 拆为 **Phase 1 MVA（4 PR，1-2 周完成）** 与 **Phase 2 Deferred（8 PR，按需启动）**。MVA 优先解决生产症状 + 验证协议层 seam 模式；Phase 2 仅在 §13.2 触发条件成立时启动。

| PR | 名称 | 依赖 | 验收命令 | 已落地 |
|---|---|---|---|---|
| **PR-0** | Audit 现状 | — | `uv run ruff check lca/plugins/seam_definitions/ lca/contracts/observability/` | ⬜ |
| **PR-1** | journal-schemas seam + schema-v2 provider | PR-0 | `uv run pytest tests/test_journal_schema.py -q` | ⬜ |
| **PR-2** | event-identities seam + identity-stable-hash provider | PR-1 | `uv run pytest tests/test_event_identity.py -q` | ⬜ |
| **PR-3** | journal-visibility seam + visibility-audience-domain provider | PR-1, PR-2 | `uv run pytest tests/test_journal_visibility.py -q` | ⬜ |
| **PR-4** | journal-transports seam + transport-sse / transport-jsonl provider | PR-1, PR-2, PR-3 | `uv run pytest tests/test_journal_transport.py -q` | ⬜ |
| **PR-5** | journal-consumer-contracts seam + consumer-lobehub / consumer-cli provider | PR-1, PR-4 | `uv run pytest tests/test_journal_consumer.py -q` | ⬜ |
| **PR-6** | manifest-derive-run provider（RunManifest 收敛到 run_seq） | PR-2 | `uv run pytest tests/test_manifest_derive.py -q` | ⬜ |
| **PR-7** | profile-snapshot seam + 迁移 plugin.inventory 到 snapshot | PR-1 | `uv run pytest tests/test_profile_snapshot.py -q` | ⬜ |
| **PR-8** | ledger migrate（顶层 lca_journal.jsonl v1 → v2） | PR-1 | `uv run python scripts/migrate_journal_v1_to_v2.py --target traces/lca_journal.jsonl` | ⬜ |
| **PR-9** | consumer-lobehub TypeScript SDK 生成器（contract → TS） | PR-5 | `pnpm run typecheck && pnpm run test:lobehub-contract` | ⬜ |
| **PR-10** | golden fixture + 契约测试 | PR-5, PR-9 | `uv run pytest tests/test_sse_projection_contract.py -q` | ⬜ |
| **PR-11** | 文档与 ADR 程序更新（AGENTS.md / docs/specs/sse-consumer-contract.md） | PR-10 | `uv run scripts/verify_md_links.py && uv run scripts/verify_doc_budgets.py` | ⬜ |
| **PR-12** | 退役旧机制（terminal_event_id fallback / data.data 字段名 / `_TEXT_CHANNEL_ALL` 硬推） | PR-6, PR-11 | `uv run ruff check --fix . && uv run pytest -q` | ⬜ |

### 6.1 PR-0：Audit 现状

**目标**：把所有 21 条根因映射到 12 PR，确认无遗漏。

**执行**：
```bash
uv run python scripts/route_legacy_patterns.py --report audit-0096.md
uv run ruff check lca/plugins/seam_definitions/ lca/contracts/observability/
uv run vulture lca/plugins/seam_definitions/ lca/contracts/observability/ --min-confidence 80
```

**输出**：`audit-0096.md` 列出每个机制的当前位置 + 改造目标 + 涉及 PR。

### 6.2 PR-1：journal-schemas seam + schema-v2 provider

**目标**：envelope schema 从 dataclass 升到 Pydantic v2 + 版本化 + 迁移表。

**改动**：
- 新建 `lca/contracts/observability/schemas/v2.py`：`EnvelopeV2` Pydantic 模型
- 新建 `lca/plugins/seam_definitions/journal_schema.py`：seam 声明
- 新建 `lca/plugins/providers/journal_schema/v2.py`：provider 实现，字段名 `payload` 替 `data`
- 新建 `lca/contracts/observability/schemas/migrate.py`：v1→v2.0.0 迁移函数
- 修改 `lca/layer0_infra/observability/journal/journal_io.py`：`_record_to_v2` 改名为 `_record_to_v2_envelope` 并用 Pydantic 校验

**不变量**：
- 所有 envelope 字段都有显式 Pydantic 类型
- schema_version 必填
- migrate 函数是 pure function（输入 v1 dict，输出 v2 dict）

**验收**：
```bash
uv run pytest tests/test_journal_schema.py -q
uv run pytest tests/test_journal_io.py -q
```

### 6.3 PR-2：event-identities seam + identity-stable-hash provider

**目标**：event_id 在构造时闭环派生，不再 fallback；派生函数不接 float ts。

**改动**：
- 新建 `lca/plugins/seam_definitions/event_identity.py`：seam 声明
- 新建 `lca/plugins/providers/event_identity/stable_hash.py`：`_derive_event_id_stable(run_id, seq, event_type)` → sha256 hex
- 修改 `lca/layer0_infra/observability/journal/engine.py:RunStore.append`：构造 StampedEvent 时**填** event_id
- 修改 `lca/layer0_infra/observability/journal/journal_io.py`：删除 `_derive_event_id` 的 fallback 分支（stamp 已有 event_id，直接用）
- 修改 `lca/layer0_infra/observability/journal/engine.py:RunStore.seal`：同上
- 修改 `lca/layer0_infra/observability/journal/serialization.py`：导出 `current_event_identity()` 供消费者使用

**不变量**：
- `RunStore.append` 返回的 StampedEvent 必有非空 event_id
- 同一 `(run_id, seq, event_type)` 永远产同一 event_id
- `event_id` 与 `run_seq` 在 ledger 内单调同序

**验收**：
```bash
uv run pytest tests/test_event_identity.py -q
uv run pytest tests/test_journal_engine.py -q
# 断言 terminal_event_id 必有
uv run pytest tests/test_run_manifest.py::test_terminal_event_id_not_empty -q
```

### 6.4 PR-3：journal-visibility seam + visibility-audience-domain provider

**目标**：把"哪些事件能到哪些 channel"做成可替换策略。

**改动**：
- 新建 `lca/plugins/seam_definitions/journal_visibility.py`：seam 声明
- 新建 `lca/plugins/providers/journal_visibility/audience_domain.py`：默认 policy 实现
  - audience=RESTRICTED → 不进 SSE live；可进 jsonl + oTel(可选)
  - audience=DOMAIN(domain=resource) + kind=plugin(operation=plugin.inventory) → 不进 SSE live；写 profile snapshot
  - audience=DOMAIN(domain=event) → 进 SSE live
  - audience=DOMAIN(domain=run) → 进 SSE live + jsonl
- 修改 `lca/layer0_infra/observability/journal/sse_frames.py:stamped_to_sse_frame`：调用 visibility policy 过滤

**不变量**：
- `RuntimeObserved plugin.inventory` 永远不进 SSE live
- 审计/ops 模式下可强制 allow（visibility-strict provider）

**验收**：
```bash
uv run pytest tests/test_journal_visibility.py -q
uv run pytest tests/test_sse_visibility_filter.py -q
```

### 6.5 PR-4：journal-transports seam + transport-sse / transport-jsonl provider

**目标**：transport 可替换，单帧 size budget 强制。

**改动**：
- 新建 `lca/plugins/seam_definitions/journal_transport.py`：seam 声明
- 新建 `lca/plugins/providers/journal_transport/sse.py`：从 `sse_frames.py` 抽出；frame size budget 16KB；redact 默认 True
- 新建 `lca/plugins/providers/journal_transport/jsonl.py`：从 `journal_io.py` 抽出；按 schema_version 落盘
- 新建 `lca/plugins/providers/journal_transport/otel.py`：OTel exporter（继承现有）
- 修改 `gateway/runs/api.py:stream_run_live`：使用 transport-sse provider
- 修改 `gateway/runs/_journal_factory.py`：使用 transport-jsonl provider
- 修改 `_TEXT_CHANNEL_ALL` → 默认 channel = `["answer"]`（decision 走另一个 channel name）

**不变量**：
- 单 SSE 帧 > 16KB → 拒推 + 记 warn 日志（`journal_transformation`）
- redact 默认 True；ops 模式通过 profile 显式 disable
- channel 名走白名单：`answer` / `reasoning` / `tool` / `meta`

**验收**：
```bash
uv run pytest tests/test_journal_transport.py -q
uv run pytest tests/test_sse_frame_budget.py -q
```

### 6.6 PR-5：journal-consumer-contracts seam + consumer-lobehub / consumer-cli provider

**目标**：消费者契约是一等公民 seam，前端投影函数可单独测试。

**改动**：
- 新建 `lca/plugins/seam_definitions/journal_consumer.py`：seam 声明
- 新建 `lca/contracts/observability/consumer_contract.py`：`ConsumerContract` Protocol：name, schema_version, project(envelope) → Projected
- 新建 `lca/plugins/providers/journal_consumer/cli.py`：CLI 投影
- 新建 `lca/plugins/providers/journal_consumer/lobehub_contract.py`：后端侧 lobehub contract 定义（spec，**不含** 实现）
- 新建 `lca/harness/sdk/ts_consumer_gen.py`：从 lobehub_contract 自动生成 TypeScript 投影函数（**单向** lca→lobehub，不双向）
- 修改 `lobehub-ui/src/store/chat/agents/transports/lcaJournal.ts`：用生成的 `projectJournalFrameContract(frame, contract)` 替换硬编码 switch
- 修改 `deploy/lobehub/patches/runtime/lcaJournal.ts`：同步
- 修改 `deploy/lobehub/patches/runtime/LcaRunDriver.ts`：reconnect 韧性策略下沉到 `consumer_resilience.ts`（独立模块）

**不变量**：
- 投影函数输入 envelope，输出 Projected，无副作用
- consumer contract 版本号必须与 envelope schema_version 配套
- 投影错误不传播到 journal（投影失败只记 metric，不影响 ledger）

**验收**：
```bash
uv run pytest tests/test_journal_consumer.py -q
pnpm run typecheck
pnpm run test:lobehub-contract
```

### 6.7 PR-6：manifest-derive-run provider（RunManifest 收敛到 run_seq）

**目标**：RunManifest 不持硬 event_id 字符串，只持 run_seq 等 journal 主键。

**改动**：
- 新建 `lca/plugins/seam_definitions/manifest_derivers.py`：seam 声明
- 新建 `lca/plugins/providers/manifest_derivers/run.py`：从 journal + run_seq watermark 派生 RunManifest
- 修改 `lca/contracts/observability/run_manifest.py`：
  - 字段 `terminal_event_id: str = ""` → `terminal_event_seq: int = 0`
  - 字段 `terminal_event_type: str = ""`（可选，记录 AgentRunFinished / RunFinished / RunSealed）
- 修改 `gateway/runs/terminalizer.py:_record_terminal_materialization`：调用 manifest-derive-run provider
- 删除 `_terminal_event_id_for` 短路逻辑；改为 `_terminal_event_seq_for`：从 journal 倒序扫第一条 terminal type 的 stamped，取其 `seq`

**不变量**：
- RunManifest.terminal_event_seq > 0 当且仅当 run 已 finished
- RunManifest 任何字段都可从 journal 派生
- 没有任何字段是"硬 id 字符串"

**验收**：
```bash
uv run pytest tests/test_manifest_derive.py -q
uv run pytest tests/test_run_manifest.py -q
```

### 6.8 PR-7：profile-snapshot seam + 迁移 plugin.inventory

**目标**：静态元数据（plugin.inventory 等）从 journal stream 迁移到独立 snapshot。

**改动**：
- 新建 `lca/plugins/seam_definitions/profile_snapshot.py`：seam 声明
- 新建 `lca/plugins/providers/profile_snapshot/run_boot.py`：boot 时一次性写 `traces/runs/<id>/profile_snapshot.json`
- 修改 `lca/plugins/seam_definitions/observability/journal.py`：RuntimeObserved kind=plugin(operation=plugin.inventory) **不再写 journal**
- 修改 `gateway/runs/api.py`：新增 `/runs/{id}/profile` 端点返回 snapshot
- 修改 `lca-ops trace`：默认查 snapshot + journal

**不变量**：
- profile_snapshot.json 是 boot 期一次性写
- journal 不再包含 plugin.inventory 事件
- snapshot 含 plan_ref, run_id, plugins,  capabilities, control_plan

**验收**：
```bash
uv run pytest tests/test_profile_snapshot.py -q
uv run pytest tests/test_no_plugin_inventory_in_journal.py -q
```

### 6.9 PR-8：ledger migrate（顶层 lca_journal.jsonl v1 → v2）

**目标**：消除 v1/v2 双 ledger。

**改动**：
- 修改 `scripts/migrate_journal_v1_to_v2.py`：支持原地转换 + 备份
- 新建 `scripts/migrate_top_level_ledger.py`：扫描 `traces/lca_journal.jsonl`，备份到 `.bak`，迁移到 v2
- 修改 `lca/layer0_infra/observability/journal/process_journal.py`：只接受 v2 输入；v1 → 自动 migrate 一次
- 新建 `tests/test_top_level_ledger_migration.py`：断言迁移后无 v1 残留

**不变量**：
- `traces/lca_journal.jsonl` 100% v2 schema
- per-run `journal.jsonl` 100% v2 schema
- migrate 工具 idempotent

**验收**：
```bash
uv run python scripts/migrate_top_level_ledger.py
uv run pytest tests/test_top_level_ledger_migration.py -q
```

### 6.10 PR-9：consumer-lobehub TypeScript SDK 生成器

**目标**：后端 consumer contract 自动生成 TypeScript SDK，避免手写漂移。

**改动**：
- 新建 `lca/harness/sdk/ts_consumer_gen.py`：从 `lobehub_contract` 生成 `lobehub-ui/src/store/chat/agents/transports/lcaJournal.generated.ts`
- 修改 `lca/Makefile` 或 `pyproject.toml`：增加 `gen-ts-consumer` 命令
- 修改 `lca/pyproject.toml`：增加 `make gen-ts-consumer && make gen-ts-consumer-verify` 到 lint 链
- 修改 `lobehub-ui/package.json`：增加 `prebuild` hook 跑 `gen-ts-consumer`

**不变量**：
- 生成文件 git 追踪（透明）
- 手写 lcaJournal.ts 只保留 consumer 韧性策略（backoff/dedup/max_retry），不含投影逻辑

**验收**：
```bash
make gen-ts-consumer
pnpm run typecheck
uv run pytest tests/test_ts_consumer_gen.py -q
```

### 6.11 PR-10：golden fixture + 契约测试

**目标**：协议升级路径有自动化守门。

**改动**：
- 新建 `tests/fixtures/journal_v2_golden/run_302c22421883.jsonl`：固定 207 帧 v2 envelope
- 新建 `tests/fixtures/journal_v2_golden/expected_projection.json`：期望投影输出
- 新建 `tests/test_sse_projection_contract.py`：固定 fixture → 调 consumer contract → 期望匹配
- 新建 `tests/test_envelope_schema_compatibility.py`：schema v1 ↔ v2 ↔ v3 兼容性矩阵
- 修改 `pyproject.toml`：`pytest` 默认包含这些文件
- 修改 `.github/workflows/ci.yml`：契约测试 gate

**不变量**：
- fixture 文件 git 追踪，PR 改 fixture 必须改 ADR
- envelope schema_version 变更必改 fixture
- 契约测试 fail-fast，无 skip

**验收**：
```bash
uv run pytest tests/test_sse_projection_contract.py -q
uv run pytest tests/test_envelope_schema_compatibility.py -q
```

### 6.12 PR-11：文档与 ADR 程序更新

**目标**：把协议升级路径写进 AGENTS.md + 新增 spec。

**改动**：
- 修改 `AGENTS.md`：§2.3 加 "Journal Protocol Layer" 一节
- 新建 `docs/specs/sse-consumer-contract.md`：consumer contract spec，引用 schema v2 + 投影规则
- 新建 `docs/specs/journal-protocol-migration.md`：升级流程（改 schema → 改 fixture → 改 contract → 改 profile → 改 ADR）
- 修改 `scripts/verify_doc_budgets.py`：加新文档到预算清单
- 修改 `scripts/check_*.py`：加 `check_protocol_schema_version.py`——禁止 envelope 字段名漂移（`data.data`、缺 schema_version 等）

**不变量**：
- 任何 protocol 改动必触发 spec 更新
- spec 与 ADR 互引

**验收**：
```bash
uv run scripts/verify_md_links.py
uv run scripts/verify_doc_budgets.py
uv run scripts/check_protocol_schema_version.py
```

### 6.13 PR-12：退役旧机制

**目标**：删除所有 fallback 与残留硬编码。

**改动**：
- 删除 `lca/layer0_infra/observability/journal/journal_io.py:_derive_event_id`（已不需要；identity provider 自带）
- 删除 `gateway/runs/terminalizer.py:_terminal_event_id_for`（改用 _terminal_event_seq_for）
- 删除 `deploy/lobehub/patches/runtime/lcaJournal.ts:parseSseBlock` 旧 fallback（用生成的 contract SDK）
- 删除 `_TEXT_CHANNEL_ALL` 常量
- 修改 `lca/contracts/observability/run_manifest.py`：删除 `terminal_event_id` 字段
- 修改 `gateway/runs/api.py:iter_live_sse`：redact 默认 True
- 修改 `lca/layer0_infra/observability/journal/journal_io.py:_record_to_v2`：删除 `data` 字段，全部用 `payload`

**不变量**：
- 任何 fallback / 容错代码都必须有 ADR 论证
- 任何 `event_id` 字段都不在 derived view 出现
- 任何 envelope 都不缺 `schema_version`

**验收**：
```bash
uv run ruff check --fix .
uv run ruff format .
uv run lint-imports
uv run mypy lca
uv run pytest
uv run vulture lca --min-confidence 80
```

---

## 7. 验收规约

> **完成本 ADR 的判定不是"12 PR 都标 Done"**，而是 §7.1~§7.6 全部 V（Value）/ CV（Contract Verification）通过。每条 V/CV 对应一条 `uv run …` 命令；命令输出符合预期 = 通过。

### 7.1 V-Schema

- **V1**：envelope 顶层 Pydantic 类型 100% 覆盖；`schema_version` 必填
  - 命令：`uv run pytest tests/test_journal_schema.py::test_envelope_schema_version_required -q`
- **V2**：v1 envelope migrate 到 v2.0.0 后所有字段类型一致
  - 命令：`uv run pytest tests/test_envelope_schema_compatibility.py::test_v1_to_v2_migration -q`
- **CV3**：CI 拦截 envelope 字段名漂移（`data.data`、缺 `schema_version` 等）
  - 命令：`uv run scripts/check_protocol_schema_version.py`

### 7.2 V-Identity

- **V4**：内存 StampedEvent 与磁盘 envelope 的 event_id 100% 一致
  - 命令：`uv run pytest tests/test_event_identity.py::test_memory_disk_consistency -q`
- **V5**：同 `(run_id, seq, event_type)` 跨进程/跨 replay 产同 event_id
  - 命令：`uv run pytest tests/test_event_identity.py::test_stable_hash_deterministic -q`
- **V6**：RunManifest.terminal_event_seq > 0 iff run finished
  - 命令：`uv run pytest tests/test_run_manifest.py::test_terminal_event_seq_set_after_finish -q`

### 7.3 V-Visibility

- **V7**：`RuntimeObserved plugin.inventory` 永远不进 SSE live
  - 命令：`uv run pytest tests/test_sse_visibility_filter.py::test_plugin_inventory_excluded -q`
- **V8**：单 SSE 帧 > 16KB → 拒推 + 记 warn 日志
  - 命令：`uv run pytest tests/test_sse_frame_budget.py::test_oversized_frame_rejected -q`
- **V9**：decision channel 文本不被静默 ignore，UI 区分显示
  - 命令：`uv run pytest tests/test_consumer_channel_distinction.py -q`

### 7.4 V-Transport

- **V10**：transport-sse redact 默认 True；ops 模式显式 False
  - 命令：`uv run pytest tests/test_journal_transport.py::test_sse_redact_default -q`
- **V11**：transport-jsonl 与 transport-sse 共享 visibility policy
  - 命令：`uv run pytest tests/test_journal_transport.py::test_visibility_shared -q`

### 7.5 V-Consumer

- **V12**：consumer-lobehub projection 由 TS SDK 生成（git 追踪）
  - 命令：`make gen-ts-consumer && git diff --exit-code lobehub-ui/src/store/chat/agents/transports/lcaJournal.generated.ts`
- **V13**：契约测试通过 golden fixture
  - 命令：`uv run pytest tests/test_sse_projection_contract.py -q`
- **V14**：reconnect 韧性（backoff / dedup / max_retry）下沉到 `consumer_resilience.ts`
  - 命令：`pnpm run test:lobehub-resilience`

### 7.6 V-Manifest

- **V15**：RunManifest 无 `terminal_event_id` 字段
  - 命令：`uv run pytest tests/test_run_manifest.py::test_no_terminal_event_id_field -q`
- **V16**：RunManifest 100% 可从 journal 派生（无硬编码字段）
  - 命令：`uv run pytest tests/test_manifest_derive.py::test_pure_derivation -q`

### 7.7 V-Ledger

- **V17**：`traces/lca_journal.jsonl` 100% v2 schema
  - 命令：`uv run pytest tests/test_top_level_ledger_migration.py::test_no_v1_remaining -q`
- **V18**：plugin.inventory 不再出现在任何 journal.jsonl
  - 命令：`uv run pytest tests/test_no_plugin_inventory_in_journal.py -q`

### 7.8 V-Doc

- **V19**：`docs/specs/sse-consumer-contract.md` 存在且通过 markdown 链接校验
  - 命令：`uv run scripts/verify_md_links.py`
- **V20**：AGENTS.md §2.3 有 Journal Protocol Layer 章节
  - 命令：`grep -q "Journal Protocol Layer" AGENTS.md`
- **V21**：`docs/specs/journal-protocol-migration.md` 存在
  - 命令：`test -f docs/specs/journal-protocol-migration.md`

---

## 8. 替代方案

### 8.1 不做 ADR，只加 fixture

**评估**：拒绝。fixture 是工具，不是 SSOT；只加 fixture 不解决"协议升级跨仓通知"问题，机制 A/B 仍存在。

### 8.2 把 consumer contract 放在前端代码仓

**评估**：拒绝。前端仓是另一个 repo，SSOT 必须在 LCA 单仓（继承 ADR-0063 I7）。TypeScript SDK 是单向生成（lca→lobehub），不双向。

### 8.3 沿用 v1 envelope 名（data 改回 event）

**评估**：拒绝。v1 envelope 嵌套在 `event` 字段下，与 v2 的 `descriptor.type` 重复，是历史包袱。v2.0.0 改名为 `payload` 是机制 U 的解。

### 8.4 不引入 visibility policy，让每个 transport 自己过滤

**评估**：拒绝。这是把"分散的不变式"重新分散（继承 ADR-0085 §3 seam/producer 责任划分）。所有 transport 必须共享同一 visibility 策略。

### 8.5 保持 terminal_event_id 字符串，加 file fallback

**评估**：拒绝。机制 E 的根因是 derived view 持硬字段，加 fallback 治标。改成 `terminal_event_seq` 是正路。

---

## 9. 风险与回滚

| 风险 | 概率 | 影响 | 回滚 |
|---|---|---|---|
| Golden fixture 写错导致 CI 永远红 | 中 | 中 | fixture 在 git 追踪，回滚一个 PR 即恢复 |
| TypeScript SDK 生成器产出 bug | 低 | 中 | SDK 也是 git 追踪，生成文件可手改（带 // generated 标记） |
| v1 → v2 migrate 漏字段 | 低 | 高 | 备份 `.bak` 文件；migrate 工具 idempotent |
| visibility policy 默认过严导致 ops 工具失明 | 中 | 中 | 备 visibility-strict provider，profile 默认 audit 模式加载 |
| LobeHub UI 项目不是 cordis，无法直接消费 seam | 高 | 低 | TS SDK 单向生成，UI 项目独立；只在 integration test 层验证 |

---

## 10. ADR 程序变更（本 ADR 落地后）

任何 envelope schema 改动必走：
1. 修本 ADR §6 加 PR（不是直接改代码）
2. 同时改 fixture
3. 同时改 consumer contract
4. 同时改 profile（如启用新 schema_version）
5. CI gate：`check_protocol_schema_version.py` 拦截残留

任何 visibility policy 改动必走：
1. 修本 ADR §3.4 七层 seam
2. 加 visibility provider 或修改现有 provider
3. fixture 中加入对应测试帧
4. profile 中显式声明（默认 policy 不静默切换）

任何 consumer contract 改动必走：
1. 修 `lca/contracts/observability/consumer_contract.py`
2. 重跑 `gen-ts-consumer`
3. fixture 更新
4. lobehub 仓 PR 同步更新生成的 SDK

---

## 11. 与既有 ADR 的关系

| 既有 ADR | 关系 | 处理 |
|---|---|---|
| ADR-0037 Journal-as-Truth | 强化 | I1 直接继承 |
| ADR-0063 统一运行事件账本 | 强化 | L1 journal-core 不动 |
| ADR-0066~0069 / 0074 插件一切 | 强化 | 七层 seam 都按 ADR-0074 范式 |
| ADR-0082 架构审查 | 协同 | 本 ADR 解决其中"协议层不是 seam"问题 |
| ADR-0084 插件架构审计 | 协同 | 本 ADR 解决其中"consumer contract 缺失"问题 |
| ADR-0085 一切插件解读 | 强化 | 本 ADR 是其"协议层"的实例化 |

---

## 12. 元数据

- 作者：LCA 架构
- 日期：2026-08-28
- 状态：**Accepted**（含 §13 两阶段拆分修订）
- 关联 ADR：0037, 0061, 0062, 0063, 0066~0069, 0074, 0082, 0084, 0085
- 关联 plan：`docs/plans/adr-0096-implementation-tracker.md`（覆盖 MVA 4 PR 详细步骤 + Phase 2 8 PR 触发条件）
- 关联宪法条款：C3 / C4 / C5 / C6 / C7
- 关联 spec：新建 `docs/specs/sse-consumer-contract.md`, `docs/specs/journal-protocol-migration.md`
- 关联 seam：MVA 阶段新建 4 个（journal_schema / event_identity / profile_snapshot / journal_consumer）；Phase 2 阶段按需新增 3 个（journal_visibility / journal_transport / manifest_derivers）
- 关联 provider：MVA 阶段新建 3 个（schema-v2 / identity-stable-hash / profile-snapshot-boot）；Phase 2 按需新增（visibility-audience-domain / transport-sse / transport-jsonl / consumer-lobehub 完整版 / manifest-derive-run）
- 关联测试：MVA 阶段新建 4 个 + 改造 2 个；Phase 2 阶段按需新增
- 落地策略：见 §13（MVA 4 PR 优先解决生产症状；Phase 2 按需启动）

---

## 13. 两阶段实施：Phase 1 MVA（最小可行架构）+ Phase 2 Deferred（按需演进）

> **2026-08-29: §13 Deferred path retired (see ADR-0099)**

### 13.1 为什么拆两阶段

§6 列出的 12 PR 实施序列在架构方向上正确，但**一次性引入 7 个新 seam + 6 个新 provider** 在当前仓存在三个具体风险：

1. **Seam 膨胀**：仓内 `lca/plugins/seam_definitions/` 已存在约 30 个 seam。每多一个 seam 都增加 profile 装配面、测试矩阵、文档预算。一次 7 个打包引入会让 Profile YAML 装配决策面指数膨胀。
2. **生产症状不能等 12 PR 完成**：LobeHub 流式文本为空的生产症状当前已在发生。MVA 优先把症状修掉，剩余 seam 按需演进。
3. **跨仓协同成本**：PR-5/PR-9 涉及 LobeHub 仓的 TS SDK 生成与 patch 同步，是单点阻塞。MVA 阶段就建立 SDK 生成器骨架 + consumer contract，让 LobeHub 端从一开始就消费生成代码，避免 Phase 2 重新协商接口。

### 13.2 Phase 1：MVA（4 PR，预计 1-2 周完成）

**目标**：修复生产症状 + 验证协议层 seam 模式可行性 + 收掉 §1.3 表中标注 ★ 的最关键根因机制。

| MVA PR | 对应 §6 PR | 关键交付 | 修掉哪些根因机制 | 验收口径 |
|---|---|---|---|---|
| **MVA-1** | PR-1 + PR-9 子集 | (a) `journal-schemas` seam + `schema-v2.0.0` provider（Pydantic v2 模型 + 迁移表）；(b) 改造 `journal_io.py` 使用 `EnvelopeV2` 校验；(c) LobeHub 端 `lcaJournal.ts` v2 兼容 patch（**手写最小版**，Phase 2 替换为 SDK 生成） | ★ A, ★ B, U, O | V1, V2, V3 |
| **MVA-2** | PR-2 全量 | (a) `event-identities` seam + `identity-stable-hash` provider（sha256(run_id, seq, type) 派生，**不接 float ts**）；(b) `RunStore.append` 闭环填 `event_id`；(c) `RunStore.seal` 同步；(d) 删除 `_derive_event_id` 的 fallback 分支 | ★ D, ★ F, P | V4, V5, V6 |
| **MVA-3** | PR-7 全量 | (a) `profile-snapshot` seam + `profile-snapshot-boot` provider（boot 期一次性写 `traces/runs/<id>/profile_snapshot.json`）；(b) 改造 `observability/journal.py`：RuntimeObserved kind=plugin(operation=plugin.inventory) **不再写 journal**；(c) 新增 `/runs/{id}/profile` endpoint | ★ C, ★ N, R | V18（plugin.inventory 不再出现） |
| **MVA-4** | PR-5 子集 + PR-9 子集 + PR-11 子集 | (a) `journal_consumer` seam + `ConsumerContract` Protocol；(b) `consumer-lobehub` 后端侧 spec（**不含前端实现**）；(c) 最小 TS SDK 生成器（lca → lobehub 单向）；(d) `consumer_resilience.ts` 模块（backoff / dedup / max_retry）；(e) LobeHub `lcaJournal.ts` + `LcaRunDriver.ts` 切换到生成 SDK + 韧性模块 | ★ I, ★ L, ★ Q, M（修复生产症状） | V12, V13, V14 |

**MVA 完成后可达状态**：

- LobeHub 流式文本正常显示（生产症状修复）
- `event_id` 内存与磁盘 100% 一致；同 `(run_id, seq, event_type)` 跨进程稳定
- `plugin.inventory` 不再撑爆 SSE 帧（改为 boot 期 snapshot）
- 协议层有 4 个真实 seam（journal_schema / event_identity / profile_snapshot / journal_consumer）；剩余 3 个 seam（journal_visibility / journal_transport / manifest_derivers）按需新增
- 链路日志四键契约（trace_id / plan_ref / event_id / schema_version）在 MVA-1/MVA-2 阶段强制建立

### 13.3 Phase 2：Deferred（8 PR，按需启动）

**触发原则（YAGNI 友好）**：每个 Phase 2 PR 仅在出现**第二个真实需求**时启动（"第二个"指除已修问题之外的第二个独立场景）。**Phase 1 完成后，所有 envelope / identity / visibility / transport / consumer 字段变更必须先开新 ADR 或修订本 ADR**，由 §10 程序强制。

| Phase 2 PR | 对应 §6 PR | 触发条件（出现下列任意一条即启动） |
|---|---|---|
| **P2-1 visibility policy 通用化** | PR-3 | (a) 出现第 2 个 `audience != DOMAIN(event)` 的事件类型需要差异化路由；或 (b) 出现需要按 audience 维度订阅 SSE 帧的运维场景 |
| **P2-2 transport 拆三家** | PR-4 | (a) 需要独立 OTel exporter；或 (b) 需要 jsonl 单独 schema 版本控制；或 (c) 第 2 个 transport 协议（如 WebSocket）出现 |
| **P2-3 manifest deriver 独立 provider** | PR-6 | (a) RunManifest 字段增加 ≥2 个非 `run_seq` 主键字段；或 (b) 出现除 RunManifest 之外的 derived view（TraceReport 等）需要同一 provider 路径 |
| **P2-4 ledger migrate 顶层切换** | PR-8 | (a) 出现 v1 数据需要被新查询路径访问；或 (b) `traces/lca_journal.jsonl` 大小超过单文件阈值 |
| **P2-5 golden fixture 完整化** | PR-10 部分 | MVA-1/MVA-4 阶段已建立 minimal fixture；Phase 2 扩为完整 envelope v1↔v2↔v3 兼容性矩阵 |
| **P2-6 spec + ADR 程序文档化** | PR-11 | MVA-4 阶段已写最小 spec；Phase 2 扩为完整 `sse-consumer-contract.md` + `journal-protocol-migration.md` |
| **P2-7 退役旧机制** | PR-12 | MVA 全部完成后统一清理 fallback / 硬编码 / `_TEXT_CHANNEL_ALL` 等遗留 |
| **P2-8 TS SDK 生成器完整版** | PR-9 完整 | MVA-4 已包含最小生成器；Phase 2 扩为完整 codegen（含 resilience + consumer 全部 event 类型） |

**Phase 2 启动路径**：

1. 触发条件成立 → 新开 ADR（或本 ADR 修订章节）
2. 该 ADR §6 中追加对应 PR
3. 同步更新 `docs/plans/adr-0096-implementation-tracker.md`（保留历史 + 标注 "Phase 2 PR-X 启动"）
4. 按 §13.4 验收口径逐项通过
5. 该 PR 完成后，本 ADR §13.2 表格中对应行的"触发条件"列归档为 "已触发于 <日期>：<原因>"

### 13.4 MVA 验收口径

MVA 整体完成 = §7 中下述条目通过：

| 条目 | 验证命令 | 对应 MVA PR |
|---|---|---|
| **V1** schema_version 必填 | `uv run pytest tests/test_journal_schema.py::test_envelope_schema_version_required -q` | MVA-1 |
| **V2** v1→v2 migrate 字段类型一致 | `uv run pytest tests/test_envelope_schema_compatibility.py::test_v1_to_v2_migration -q` | MVA-1 |
| **V3** CI 拦截字段名漂移 | `uv run scripts/check_protocol_schema_version.py` | MVA-1 |
| **V4** event_id 内存磁盘一致 | `uv run pytest tests/test_event_identity.py::test_memory_disk_consistency -q` | MVA-2 |
| **V5** event_id 跨进程稳定 | `uv run pytest tests/test_event_identity.py::test_stable_hash_deterministic -q` | MVA-2 |
| **V6** terminal_event_seq > 0 iff finished | `uv run pytest tests/test_run_manifest.py::test_terminal_event_seq_set_after_finish -q` | MVA-2 |
| **V7** plugin.inventory 不进 SSE live | `uv run pytest tests/test_sse_visibility_filter.py::test_plugin_inventory_excluded -q` | MVA-3 |
| **V12** consumer-lobehub projection 由 TS SDK 生成 | `make gen-ts-consumer && git diff --exit-code lobehub-ui/src/store/chat/agents/transports/lcaJournal.generated.ts` | MVA-4 |
| **V13** 契约测试通过 golden fixture | `uv run pytest tests/test_sse_projection_contract.py -q` | MVA-4 |
| **V14** reconnect 韧性下沉 | `pnpm run test:lobehub-resilience` | MVA-4 |

V8（单帧 > 16KB 拒推）、V9（decision channel UI 区分）、V10/V11（transport 韧性）随 P2-1/P2-2 一起落地。

### 13.5 与 §6 实施序列的对应

| §6 PR | 状态 | 归属阶段 |
|---|:-:|---|
| PR-1 schema seam | ✅ | MVA-1 |
| PR-2 identity seam | ✅ | MVA-2 |
| PR-7 profile-snapshot | ✅ | MVA-3 |
| PR-5 consumer-contracts（最小） | ✅ | MVA-4 |
| PR-9 TS SDK 生成器（最小） | ✅ | MVA-4 |
| PR-11 spec（最小） | ✅ | MVA-4 |
| PR-3 visibility policy | ⏸ Deferred | P2-1 |
| PR-4 transport 三家 | ⏸ Deferred | P2-2 |
| PR-6 manifest deriver | ⏸ Deferred | P2-3 |
| PR-8 ledger migrate | ⏸ Deferred | P2-4 |
| PR-10 golden fixture（完整） | ⏸ Deferred | P2-5 |
| PR-11 spec（完整） | ⏸ Deferred | P2-6 |
| PR-12 退役旧机制 | ⏸ Deferred | P2-7 |
| PR-9 TS SDK（完整） | ⏸ Deferred | P2-8 |

MVA 完成时 §6 表"已落地"列填 ✅ 的为 5 个原 PR；Phase 2 启动时逐个填 ✅。