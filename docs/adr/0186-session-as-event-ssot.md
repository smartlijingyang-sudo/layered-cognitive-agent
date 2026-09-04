# ADR-0186 — Session 为事件 SSOT：append + observer + fold

## 状态

Proposed（2026-09-04 起草）。实施按 §5 PR-3a–3i 推进；本 PR-3i 只落 ADR 草稿、配套 Note 与架构不变量骨架。

**延伸**：ADR-0183（事件总线框架 + 单 SSOT）、ADR-0184（事件生命周期受管理投递）。

**互补（不改正文）**：ADR-0185（Model-Visible 走统一 event bus 的 producer + fold 重建）。0185 锁 model-visible **生产语义**；本 ADR 锁 **Session 真值层**（谁拥有 in-process log、谁落盘、谁 fold）。

**对齐参考**：deepseek-harness `packages/core/session/src/index.ts` — `Session.append` → in-memory log push → fire `session/event` observer；`foldRequestHeader` / `foldSurface` 纯函数重建；`JsonlSessionPersistence` 作为 observer 写盘。`AGENTS.md`：**Model-visible ⟺ logged**。

**本文档配套 Note**：[`docs/notes/implemented/seam/2026-09-04-session-as-event-ssot.md`](../notes/implemented/seam/2026-09-04-session-as-event-ssot.md)。

## 0. 决策摘要

把 LCA 事件真值从「`EventBus.publish` 入队 + PersistenceWorker / SpineSink 写盘」提升为 DSH 形态的有状态 **Session**：

```text
Session.append(type, data)
  ├─ JSON / surface 校验 + 拒重入
  ├─ deepFreeze → log.push(event)     ← in-process SSOT
  ├─ fire SessionObserver (contained) ← Persistence / metrics / …
  └─ return event

fold*(snapshot_events())              ← 纯函数派生（无 I/O）
JsonlSessionPersistence.on_session_event → <run_id>.spine.jsonl  ← durable SSOT
```

| 角色 | 拥有 | 不做 |
|---|---|---|
| `Session` | in-memory append-only log + 增量 fold 缓存 | 不知 JSONL / fsync / zstd |
| `SessionStore` | create / restore / dispose | 不知落盘格式 |
| `SessionObserver`（含 Persistence） | 订阅 append 后通知；落盘 / 导出 | 不知 fold / surface |
| fold 纯函数 | 从事件流重建 header / surface / step_tree | 无 I/O、无副作用 |

**代价**：publisher / subscriber / deriver / EventSpine 入口迁到 Session；`DeliveryQueue` / `NotificationBus` / 总线内嵌 PersistenceWorker 降级或删除。

**收益**：真值位置与 DSH 对齐；append 提交与 observer 失败解耦；派生走 fold，消除 in-memory callback 与落盘事实分叉；ADR-0185 model-visible fold 落在同一 Session 真值层上。

## 1. 背景与现状（事实）

### 1.1 真值位置错位

| | DSH | LCA 现状 |
|---|---|---|
| in-process 真值 | `Session.log`（append-only array） | 无等价实体；`EventBus` 是无状态 dispatch |
| 持久化 | `session/event` observer（`JsonlSessionPersistence`） | `PersistenceWorker` / `SpineSink` 挂在 bus 下游 |
| 派生 | `foldRequestHeader` / `foldSurface` 纯函数 | `EventSpine._subscribers` in-memory callback + 部分 fold（0185） |
| flush | `session/flush` parallel await 全部 listener | `PersistenceWorker.flush()` 只刷自身 |
| 失败边界 | observer 失败 contained，不回滚已 commit 的 append | sink fail-fast / subscriber contained 混在 bus 路径 |

证据链路：ADR-0184 记录的投递黑洞（零 sink 静默）；`step_tree_accumulator` 订阅 in-memory 流与落盘事实不重合（H-seg / `steps=[]`）。

### 1.2 与既有 ADR 的缝

| ADR | 已锁 | 本 ADR 补的缝 |
|---|---|---|
| **0183** | `EventBus.publish` 唯一生产入口；`<run_id>.spine.jsonl` durable SSOT；I-FW-BUS-* / I-FW-SSOT-* | 公开生产入口升为 `Session.append`；bus 降为 Session 内部命令面；durable SSOT 仍为 spine.jsonl，由 PersistenceObserver 镜像 |
| **0184** | 四段投递（ACCEPT / RECORD / PERSIST / DELIVER）；I1 装配 / I2 必落 / I3 写实例唯一 | RECORD = log.push；PERSIST / DELIVER = observer；`session/flush` 覆盖全部 PersistenceObserver |
| **0185** | model-visible producer + `foldRequestHeader`；删旁路 `model_visible/` | 不改 0185 正文；Session 成为 append 目标与 fold 输入源 |

不新开平行 event schema / Journal 词表；扩展既有 Protocol / Plugin / fold 缝。

## 2. 第一性原理

### 2.1 真正发生的三件事

1. **生产**：某边界把事实追加进有序日志。
2. **持久化**：日志增长后，observer 把同一事件耐久化（可换后端）。
3. **派生**：任意时刻从日志快照 fold 出 header / surface / step_tree / 投影。

### 2.2 最干净的机制边界

- **真值拥有者**：`Session`（in-process）+ PersistenceObserver 写出的 `<run_id>.spine.jsonl`（durable）。
- **投影方**：viewer / explain / replay / deriver — 只读 `snapshot_events()` 或 SpineReader，再 fold。
- **副作用**：仅 Persistence / exporter 类 observer；fold 零副作用。

### 2.3 不变量预告（§4）

`I-SESSION-1` 生产入口唯一 · `I-SESSION-2` fold 无 I/O · `I-SESSION-3` 业务禁直写 spine · `I-SESSION-4` 持久化是 observer · `I-SESSION-5` deriver 走 fold。

## 3. 设计

### 3.1 Session 契约（PR-3a）

`lca_kernel/events/session.py`（契约先行，实现在 PR-3c）：

- `SessionHeader` / `SessionEvent` — frozen dataclass
- `SessionObserver` Protocol — `on_session_event(session, event)`；失败 contained
- `SessionProtocol` — `append` / `event_at` / `snapshot_events` / `request_header` / `step_tree` / …
- `SessionReentryError` — append 重入拒绝

对齐 DSH `SessionEventMap` 形态：`type: str` + `data: dict`；与 `SpineEventRecord` 解耦（in-memory vs 落盘字节布局，经 projection 映射）。

### 3.2 fold 纯函数（PR-3a，复用 0185 fold）

`lca_kernel/events/fold.py` 已有 `canonicalHeader` / `headerEquals` / `foldRequestHeader`（ADR-0185 PR-0）。本 ADR 要求：

- fold 模块保持纯函数（I-SESSION-2）
- 增补 `foldStepTree` / `foldSurface`（或等价）供 deriver 切流（PR-3g）
- Session 增量 fold 缓存（`requestHeader()` 风格）与离线 `fold*(events)` 语义一致

### 3.3 Session runtime plugin（PR-3c）

`lca/plugins/session/runtime/`：`Session` 实现 + `SessionStore`；boot 注册。唯一 `Session(...)` 创建入口。

### 3.4 PersistenceObserver（PR-3e / 3e–3f）

- `PersistenceWorker` → `PersistenceObserver` 基类（SessionObserver）
- `lca/plugins/session/persistence_jsonl/`：`JsonlSessionPersistence`（对齐 DSH）
- bus 不再 `mount_sink` 作为主写路径；写盘只在 observer 内
- partial-write 回滚 / torn detection / `session/flush` parallel await — 按 DSH 语义落地，细节在 PR-3e 验收

### 3.5 生产 / 消费迁移动作

| 现有 | 目标 |
|---|---|
| 16+ publisher 调 `bus.publish` | 调 `Session.append`（Session 内可再走鉴权 / envelope） |
| `SpineFileSink` / `JournalSink` / `ConsoleProjector` / `SpineChainSink` / step_tree subscriber | `Session.observe` |
| `step_tree_accumulator` / narrative / graph / live_tail / anomaly / otel / waterfall / emit_pipeline（`EventSpine.subscribe`） | fold + `snapshot_events` / SpineReader |
| `EventSpine.append` / `spine_port_append` 公开面 | Session.append shim（PR-3h）；compat 带 delete-when |

### 3.6 与 ADR-0185 的接缝

- model-visible 仍由 `ModelVisiblePublisher` / Hook 生产（0185 I-MV-* 不变）
- 生产落点从「只经 EventBus → SpineSink」迁到「`Session.append` → PersistenceObserver → spine.jsonl」
- `foldRequestHeader` 输入源仍是同一 durable 链；Session 增量 fold 与离线 fold 共用纯函数
- **禁止**改 ADR-0185 正文；接缝说明只写在本 ADR 与 Note

## 4. 不变量（I-SESSION-1..5）

| ID | 内容 | 测试位置 | 落地 PR |
|---|---|---|---|
| **I-SESSION-1** | `SessionProtocol` / `Session.append` 是事件生产公开入口；业务不直调 `EventSpine.append` / `spine_port_append` / 绕过 Session 的 `bus.publish` 作为唯一真值写入 | `tests/architecture/test_session_ssot_invariants.py::test_i_session_1_*` | 3a 契约 · 3c 实现 · 3d/3h 收口 |
| **I-SESSION-2** | `lca_kernel/events/fold.py`（及后续 fold*）无文件系统 I/O、无 `print` / `logging` / `datetime.now` | `::test_i_session_2_fold_no_io`（可与 `test_session_fold_invariants` 并列） | 3a |
| **I-SESSION-3** | `lca/cognition/` / `lca/runtime/` / `lca/agent/` 禁直写 spine 落盘 API | `::test_i_session_3_no_business_direct_spine_write`（承接 I-FW-BUS-1 业务侧） | 3d / 3h |
| **I-SESSION-4** | 持久化以 `SessionObserver` 形态存在；`<run_id>.spine.jsonl` 物理写方唯一（JsonlSessionPersistence / 共享写实例）；禁止平行 PersistenceWorker 主路径 | `::test_i_session_4_persistence_is_observer` | 3e / 3f |
| **I-SESSION-5** | deriver 从 Session 快照或 SpineReader + fold 重建；禁止新挂 `EventSpine._subscribers` in-memory 派生主路径 | `::test_i_session_5_deriver_uses_fold` | 3g |

不破坏 ADR-0183 I-FW-BUS-2/3/4、I-FW-SSOT-1（durable 链仍唯一为 spine.jsonl）、ADR-0184 I1–I3 方向、ADR-0185 I-MV-1..5。

## 5. PR 切分（3a–3i）

全部独立可 revert。依赖图：

```text
PR-3a Session 契约 + fold 纯函数
  ├─→ PR-3b 删 DeliveryQueue + NotificationBus（总线内部降级）
  ├─→ PR-3c Session runtime plugin
  │     ├─→ PR-3d publishers → Session.append
  │     ├─→ PR-3e PersistenceObserver 重命名 + 接口
  │     │     └─→ PR-3f subscribers → Session.observe（含 JSONL plugin）
  │     ├─→ PR-3g deriver fold 切流
  │     └─→ PR-3h EventSpine + spine_port → Session.append shim
  └─→ PR-3i ADR-0186 草稿 + 架构不变量骨架（本 PR；可与 3a 并行）
```

| PR | 目标 | 触点（摘要） | 验收要点 | delete-when |
|---|---|---|---|---|
| **3a** | Session 契约 + fold 纯函数锚点 | `lca_kernel/events/session.py`；fold 扩展 / 单测 | Protocol importable；fold 无 I/O；契约测试绿 | N/A（加法） |
| **3b** | 删过渡态 Queue / NotificationBus | `queue.py` / `notification.py`；bus 降级 | `rg NotificationBus\|DeliveryQueue` 生产路径 = 0 | `rg` 仅测与文档；tracking ADR-0186 PR-3b |
| **3c** | Session + SessionStore plugin | `lca/plugins/session/runtime/`；boot | create / append / restore / dispose 单测 | N/A |
| **3d** | 16+ publisher 迁 `Session.append` | `lca/plugins/events/publishers/**` | 授权矩阵仍过；无直 `bus.publish` 作为业务唯一写入（compat 窗口除外） | compat shim：`rg bus.publish` 业务白名单清零，tracking ADR-0186 PR-3d |
| **3e** | PersistenceObserver 基类替换 PersistenceWorker | `lca_kernel/events/persistence.py` | observer 接口 + flush 语义单测 | `PersistenceWorker` 名：`rg` = 0，tracking ADR-0186 PR-3e |
| **3f** | subscriber / sink 迁 `Session.observe` + JSONL plugin | persistence_jsonl plugin；原 sinks/subscribers | 落盘 / fsync / 回滚场景绿 | 旧 `mount_sink` 生产路径清零，tracking ADR-0186 PR-3f |
| **3g** | deriver fold 切流 | step_tree / narrative / graph / live_tail / … | fold 重建与旧投影快照一致 | `EventSpine.subscribe(` 派生主路径 = 0，tracking ADR-0186 PR-3g |
| **3h** | EventSpine / spine_port → Session.append shim | `_spine_port.py`；EventSpine | 旧调用方行为不变；架构测试禁新直写 | shim：`rg event_spine.append\|spine_port_append` 仅 shim 内，tracking ADR-0186 PR-3h |
| **3i** | 本 ADR + Note + `test_session_ssot_invariants.py` | `docs/adr/` · `docs/notes/` · `tests/architecture/` | 索引含 0186；骨架 xfail/pass 声明清晰 | N/A（文档 + 锁） |

### PR-3i 范围（本提交）

- 新增本 ADR（Proposed）
- 新增配套 Note
- 新增架构不变量测试骨架（未落地项 `xfail(strict=False)`）
- `docs/adr/README.md` 索引一行
- **不改**运行时代码；**不改** ADR-0185 正文

## 6. 与现有 ADR / Note 的关系

| 既有 | 处置 |
|---|---|
| **ADR-0183** | **延伸**：公开 SSOT 写入面从 bus 升到 Session；durable 链仍 I-FW-SSOT-1 |
| **ADR-0184** | **延伸**：四段生命周期映射到 append commit + observer；I1/I2/I3 在 Session 装配上继续强制 |
| **ADR-0185** | **互补**：不动正文；model-visible 事件进入 Session log |
| **ADR-0073** RunSession 路径 | **不冲突**：0073 管 HTTP session 路由契约；本 ADR 管事件 log SSOT |
| **ADR-0178** 四级收敛 | **延伸**：SessionEvent 类型化承接 L2；fold / observer 承接 L3/L4 运行时边界 |
| Note `2026-09-04-model-visible-bus-alignment` | **不冲突**：0185 配套；本 Note 管 Session 真值层 |
| Note `2026-09-03-observation-convergence-root` | **延伸**：emit 单入口与 Session.append 对齐 |

## 7. 风险与回滚

| 风险 | 缓解 |
|---|---|
| 与 ADR-0183「bus 唯一入口」表述冲突 | 本 ADR 明确：公开入口 = Session.append；bus 为 Session 内部命令；I-FW-BUS-1 业务侧断言迁到禁直写 spine / 禁绕 Session |
| publisher 迁移面大（16+） | PR-3d 独立；双轨 shim + delete-when；每 PR 可 revert |
| PersistenceWorker 替换影响热路径 | PR-3e/3f 场景测 + live-run；partial-write 回滚单测先于切流 |
| deriver 切 fold 行为漂移 | PR-3g 快照比对；0185 fold parity 已作语义锚 |
| 并行 subagent 撞文件 | worktree 隔离；3i 只碰 docs + 架构测试骨架 |

**回滚**：3i 仅文档/骨架，revert 无运行时影响。其余 PR 各自独立 revert；3h shim 保证旧调用方在迁完前可回退。

## 8. 验证协议（骨架）

```sh
uv run pytest tests/architecture/test_session_ssot_invariants.py -q
./scripts/lca-ops notes-check
# 索引守护（CI）
uv run pytest tests/test_refactor_guards.py::TestAdrIndex::test_adr_index_matches_filesystem -q
```

终态（3a–3h 全合后）追加：Session create/append/restore 场景绿；live-run `spine.jsonl` 与 `Session.snapshot_events()` fold 一致；I-SESSION-1..5 全部去 xfail。
