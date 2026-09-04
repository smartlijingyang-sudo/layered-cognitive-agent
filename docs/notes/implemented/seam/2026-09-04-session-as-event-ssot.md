# Agent Note: Session 为事件 SSOT — append + observer + fold

Status: implemented

## Progress (2026-09-04)

主路径已落地。剩余两项为带 delete-when 的 COMPAT，不阻挡本 note 收口。

| 项 | 状态 | 证据 |
|---|---|---|
| `lca_kernel/events/session.py` 契约面 | 落地 | `SessionProtocol` / `SessionObserver` / `SessionEvent` / `SessionHeader` / `SessionReentryError` 已声明；`tests/lca_kernel/events/test_session_contract.py` 覆盖 |
| `lca_kernel/events/fold.py` 纯函数 | 落地 | 无 I/O / 无 `print` / 无 `logging` / 无 `datetime`；`canonicalHeader` / `headerEquals` / `foldRequestHeader` / `_sameSchema` 实现完成 |
| `lca_kernel/events/persistence.py` Observer 化 | 落地 | `PersistenceObserver` 同步落盘；已删 `DeliveryQueue` / `_consume_loop`；`/health` 与 `events-delivery` 读 Observer |
| `PersistenceWorker` 别名 | 已删 | 生产路径 `rg PersistenceWorker` = 0；I-SESSION-4 翻正 |
| `deriver` fold 切流 | 部分 | 生产 step_tree 走 `StepTreeFoldDeriver`（I-SESSION-5 通过）；`live_tail.subscribe` 是 SSE carrier fan-out，不是 EventSpine.subscribe / fold 派生主路径；旧 `StepTreeAccumulatorDeriver` 与 graph/waterfall/otel/anomaly `on_event` 留 COMPAT(delete-when: ADR-0186 PR-3g) |
| sinks/subscribers observe | 落地 | boot 只入 `_session_observe` 目录；run bind `set_session` 整表挂上；journal / spine_file / console / chain / step_tree 均无 `mount_sink`/`bus.subscribe` |
| `tests/architecture/test_session_ssot_invariants.py` | 落地 | I-SESSION-1/2/3/4/5 通过（I-SESSION-1 仅在 session 模块缺失时条件 xfail） |
| `RunEventSessionBridge.append` EventBus 双写 | COMPAT | `event_session.py` 仍 `EventBus.default().publish`；COMPAT(delete-when: Bridge.append 不再 EventBus.publish 双写, tracking: ADR-0186 PR-3f) |
| `pipeline_loader.apply_pipeline` | COMPAT | 仍 `bus.mount_sink`（平行 bus 路径；boot 生产走 `register_pipeline_once`，本函数保留声明式装配入口） |

## Problem

LCA 事件链路把 durable 文件链当作唯一真值，却缺少 DSH 式的有状态 Session：`EventBus` 是无状态 dispatch，`PersistenceWorker` / `SpineSink` 挂在总线内部，deriver 仍大量订阅 `EventSpine` in-memory callback。结果是：

1. **真值位置错位** — in-process 没有 append-only log 实体；事件离开 bus 后内存即失，恢复与 fold 只能反查盘，和 DSH「Session.log 拥有真值、persistence 是 observer」相反。
2. **持久化与投递耦合** — 写盘不是可插拔 observer，而是 bus 下游组件；零 sink / 半装配会吞事件（ADR-0184 已记投递黑洞），也没有 `session/flush` 覆盖全部 listener 的语义。
3. **派生与事实分叉** — `step_tree_accumulator` 等走 in-memory 订阅，与 PersistenceWorker 落盘序列不保证重合，形成 journal `steps=[]` / H-seg 一类症状。
4. **与 ADR-0185 的缝未钉死** — model-visible 已要求从 spine fold 重建，但缺少「谁拥有 log、谁 observe、谁 fold」的 Session 真值层 ADR；0185 只管 producer，不管 Session。

元决策见 [ADR-0186](../../../adr/0186-session-as-event-ssot.md)。本 note 是实施索引与 seam 边界说明。

## Proposal

落地 **Session 为事件 SSOT**：公开生产入口为 `Session.append`；append 提交后同步通知 `SessionObserver`（失败 contained）；持久化以 `JsonlSessionPersistence` 等 observer 写 `<run_id>.spine.jsonl`；派生一律 `fold*` 纯函数读快照 / SpineReader。按 ADR-0186 §5 的 PR-3a–3i 切开，本 note 随 3i 提出。

### 机制边界

| 对象 | 职责 |
|---|---|
| `Session` / `SessionProtocol` | in-process append-only log；增量 fold 缓存 |
| `SessionStore` | create / restore / dispose |
| `SessionObserver` | append 后通知；含 Persistence / metrics / exporter |
| `fold*` | 纯函数重建 header / surface / step_tree；无 I/O |
| durable 链 | PersistenceObserver → `<run_id>.spine.jsonl`（仍满足 ADR-0183 I-FW-SSOT-1） |

### 与 ADR-0185 的关系

- **0185**：model-visible **producer** + `foldRequestHeader`（payload 带原文、删旁路文件）。
- **0186**：Session **真值层**（append / observer / fold 宿主）。
- 不动 0185 正文；model-visible 事件经 Session.append 进入同一 log。

### PR-3a–3i（摘要）

| PR | 内容 |
|---|---|
| 3a | Session 契约 + fold 纯函数 |
| 3b | 删 DeliveryQueue + NotificationBus |
| 3c | Session runtime plugin |
| 3d | publishers → Session.append |
| 3e | PersistenceObserver 替换 PersistenceWorker |
| 3f | subscribers → Session.observe + JSONL plugin |
| 3g | deriver fold 切流 |
| 3h | EventSpine / spine_port → Session.append shim |
| 3i | 本 ADR + Note + `test_session_ssot_invariants.py` 骨架 |

### 不变量

`I-SESSION-1`..`I-SESSION-5` 见 ADR-0186 §4；骨架测试：`tests/architecture/test_session_ssot_invariants.py`。未落地项 `xfail(strict=False)`，对应 PR 收口时翻正。

## Alternatives considered

### Why not 只强化 EventBus + PersistenceWorker，不引入 Session？

事实是 bus 无状态、无 restore / 无增量 fold 缓存 / 无「append 已提交 vs observer 失败」的清晰边界。继续补丁 PersistenceWorker 只会加深「持久化是总线内部职责」。DSH 用 Session 实体一次划清真值与 observer；LCA 需要对齐同一边界，而不是再给 dispatch 中心加状态。

### Why not 把 NotificationBus / subscribe_pull 当派生通知中介？

事实是 ADR-0185 与 DSH 的派生形态是 **fold 纯函数**（拉全量或快照后 fold），不是「通知消费者来拉」的推拉混合。NotificationBus 是过渡态，增加平行机制；PR-3b 删除它。

### Why not 改 ADR-0185 正文，把 Session 写进 0185？

事实是 0185 范围是 model-visible producer + fold 重建，已 Proposed 并有独立 PR 序列。Session 真值层跨 publisher / persistence / deriver / EventSpine，属于跨 ADR 边界的元决策，应单开 0186；0185 正文保持不动，避免抢写别人 worktree 中的 ADR。

### Why not 立即删 spine.jsonl、只保留内存 log？

事实是进程崩溃后必须有 durable 链；ADR-0183 I-FW-SSOT-1 已钉 `<run_id>.spine.jsonl`。本提案保留 durable SSOT，只把 in-process 真值交给 Session，由 PersistenceObserver 镜像落盘。

## Acceptance criteria

- `docs/adr/0186-session-as-event-ssot.md` 状态 Proposed；`docs/adr/README.md` 索引含 0186
- 本 note 位于 `docs/notes/implemented/seam/`，`Status: implemented`
- `tests/architecture/test_session_ssot_invariants.py` 声明 I-SESSION-1..5；未落地用 `xfail(strict=False)` 标 PR 编号
- `uv run pytest tests/architecture/test_session_ssot_invariants.py -q` 以声明状态通过（pass 或 xfail）
- `./scripts/lca-ops notes-check` 不因本 note 失败
- Bridge.append EventBus 双写与 `apply_pipeline`→`mount_sink` 保留 COMPAT(delete-when)，不阻塞主路径收口

## Risks

| 风险 | 缓解 |
|---|---|
| 3a–3h 未合时不变量长期 xfail | 每条 xfail reason 写明翻正 PR；3i 只挂锁不装强制 fail |
| 与 I-FW-BUS-1「publish 唯一入口」表述摩擦 | ADR-0186 §6/§7 写明公开入口迁 Session；bus 降为内部命令；架构测试跟迁 |
| 并行 PR 撞 `persistence.py` / publishers | worktree 隔离；本 note / ADR 只描述矩阵，不抢改实现文件 |
| fold 扩展与 0185 fold 模块漂移 | 3a 复用既有 `fold.py`；I-SESSION-2 守纯函数 |

## Related

- [ADR-0186](../../../adr/0186-session-as-event-ssot.md)
- [ADR-0183](../../../adr/0183-event-bus-framework-ssot.md) / [ADR-0184](../../../adr/0184-event-lifecycle-managed-delivery.md) / [ADR-0185](../../../adr/0185-model-visible-event-bus-alignment.md)
- [Note: model-visible bus alignment](../../proposed/seam/2026-09-04-model-visible-bus-alignment.md)
- [Note: observation convergence root](../../proposed/seam/2026-09-03-observation-convergence-root.md)
- deepseek-harness `packages/core/session/src/index.ts`（append + observer + fold）
