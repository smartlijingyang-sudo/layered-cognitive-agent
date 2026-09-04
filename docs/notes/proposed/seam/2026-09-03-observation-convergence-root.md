# Agent Note: 观测面 / 控制面 / 状态机三方收口 — 根 note 与子 note 索引

Status: proposed

> 元决策见 [ADR-0178 观测面 / 控制面 / 状态机三方收口 — 四级收敛与单 SSOT 体系](../../../adr/0178-observation-control-state-convergence.md)。本 note 是 ADR-0178 在 LCA Notes 体系的实施索引。

## Problem

`docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md` 根 note 落地后,42 处反模式已识别、9 条 lint 守门已建、PR-1 ~ PR-2 已合。但用户 2026-09-03 反馈的 7 类症状里仍有 4 类未收口:

- **emit 现场混乱** — `runtime_loop` 4 键裸 dict vs `reflectors/runtime` 平行 `emit_exception_caught` vs `EnvelopeEmitter.emit_exception_caught` Protocol 4 个 str,3 个入口并存
- **flush 时机不透明** — `FileSink` 3 套 fd(主 ledger / exceptions index / tracing fallback)各 fd 不同 fsync 策略,文档缺失
- **payload schema 缺失** — `event_descriptor_registry` 40 行表无 schema 校验,几十处 `payload={...}` 裸 dict,`exception.caught` 缺 `traceback_text` 时 payload < 4 KiB → 不触发 offload → traceback 永久丢失
- **协议契约乱 + 双写** — `RunStatus` / `JournalRunStatus` / `RunLifecycleStatus` 三套并存;`_capture_io.to_jsonable` + `projector.to_jsonable` 双份;`events.jsonl` ↔ `<run_id>.spine.jsonl` legacy 还在

根因不是"做得不够",是**只做了一级(SSOT 字符串收口),没做 2-4 级**。Python 没有 TS 类型系统,必须 4 级分明才能逼近 DSH `SessionEventMap` 形态。

## Proposal

按 4 级收敛 + 5 子 note 实施,每个 note 独立 PR、独立 delete-when、独立 regression lock。每条 note ≤ 200 行。

### 5 项收敛原则

1. **L1 SSOT 字符串收口** — 文件名 / Status enum / Outcome enum / Locator 必须走 SSOT 函数,grep 守门。承接根 note PR-3 ~ PR-7 剩余。
2. **L2 类型化 payload** — 每个 EP 绑定 payload dataclass / TypedDict;emit 入口接收类型化 record 而非裸 dict。
3. **L3 运行时校验** — `emit_*` 入口加 schema validation(pydantic v2 或自建 `EventPayloadModel.parse_obj`),缺字段直接抛。
4. **L4 调用点类型约束** — `EnvelopeEmitter.emit_exception_caught(record: ExceptionRecord)` 而非 4-str;Protocol 签名拒绝裸 str。

### 5 子 note 索引

| # | 文件 | class | 承接 | 实施量 |
|---|---|---|---|---|
| 1 | [1-architecture-1-convergence-contract.md](1-architecture-1-convergence-contract.md) | seam | L1 剩余消费方迁移(根 note PR-3 ~ PR-7) | 中 |
| 2 | [2-seam-fsync-semantics.md](2-seam-fsync-semantics.md) | seam | L3 fd fsync 协议统一(根 note 不覆盖,**新 ADR 配套**) | 中 |
| 3 | [3-seam-emit-single-entry.md](../../implemented/seam/2026-09-03-3-seam-emit-single-entry.md) | seam | L4 emit 入口收口到 1 个 + 删 reflector 平行的 `emit_exception_caught` | 中 |
| 4 | [4-contract-payload-schema-typing.md](../contract/4-contract-payload-schema-typing.md) | contract | L2 类型化 + L3 schema validation | 大 |
| 5 | [5-runtime-invariants-and-lint.md](../runbook/5-runtime-invariants-and-lint.md) | runbook | 4 级 lint 守门规则 + runtime invariant 守门 + 防回归 | 中 |

### 实施顺序

```
note 1 (L1 收口) ──┐
                    ├─→ note 3 (emit 单入口)
note 4 (L2/L3)  ────┘         │
                              ↓
note 5 (lint 守门) ←──── note 2 (fsync 语义)
```

- **note 1** 与 **note 4** 可并行(互不依赖)
- **note 3** 依赖 note 1 + note 4(emit 入口收口需要消费方先 SSOT + payload 类型化)
- **note 2** 独立(只是 fsync 协议,与 emit 解耦)
- **note 5** 必须在最后(守门要在所有反模式都迁完后才能有效)

### Delete-when 原则

每条子 note 内的 compat shim / 平行路径 / legacy alias 必须按 AGENTS.md §1 模板填:

```text
# COMPAT(delete-when: <具体条件>, tracking: ADR-0178-<note-id>)
```

条件三类之一:
- 稳定 ≥ 14 天且无 caller
- 消费者全部迁移完毕(rg 零非文档命中)
- 配套新 ADR 已 Accepted 且旧实现零调用

**无 delete-when = 红**:PR 必须补 ADR 或删除。

## Alternatives considered

### Why not 只做一级(只继续推 PR-3 ~ PR-7)?

事实是:**一级收敛已推到 42 处反模式识别 + 9 条 lint**,再做也只是"补一级覆盖率"。**不会解决**用户列的"traces/runs 下不全 + traceback 缺失"——这两个症状的物理原因在 fsync 语义(不在 SSOT)+ payload schema(不在 SSOT)。**只做一级等于让 ADR-0178 沦为根 note 的扩展 PR,而不是元决策**。

### Why not 一次性 4 级合并 1 个大 PR?

违反 AGENTS.md §1 "契约改动必须同 PR 改实现 + 测试" + "1-3 PR 列表"。4 级跨 contracts / infrastructure / runtime / scripts 4 个 seam + ≥ 13 文件,**单 PR 不可审、不可回滚**。分 5 子 note 是 AGENTS.md §1 硬约束的体现,不是过度细分。

### Why not 不开 ADR,直接写 note?

`docs/notes/README.md §1` 明确:改变其他 ADR 边界(本 ADR 扩展 ADR-0169 D8–D10 / 形变 ADR-0176 D5 / 扩展 ADR-0177)的决策**走 ADR**。Notes 体系只承接"不改 ADR 边界的单点决策"。不开 ADR 等于绕过 README §1 与 write-note skill 的硬约束。

### Why not 不动 Body / Brain / Runtime 状态机?

用户 2026-09-03 反馈的 7 类症状集中在"emit / 写日志 / flush / 字段"——**全在观测面 + 控制面 + 状态机面**。Body / Brain / Runtime 状态机的双写 / 平行 emitter 症状本次未列出,属于后续独立 ADR 范围。本次只收"用户实际痛点"。

## Acceptance criteria

整体 4 级收敛落地的可观察状态:

1. `scripts/check_observation_ssot.py` 9 + 4 = 13 条 lint,0 命中
2. `scripts/check_runtime_invariants.py` 新建,≥ 3 条 invariant,0 命中
3. `rg "emit_exception_caught" lca/` 命中数 = 1(仅 SSOT 文件),`rg "from .*reflectors.*emit_" lca/` = 0
4. `rg "payload\s*=\s*\{" lca/infrastructure/observability/` 命中数 ≤ 1(SSOT 文件内的 `EventPayloadModel` 默认值定义)
5. `FileSink.__init__` 接受 `fsync_protocol: Literal["per-write", "batch", "commit"]` 枚举参数,3 套 fd 走同一参数
6. `EnvelopeEmitter.emit_exception_caught(record: ExceptionRecord)` 1 个签名;`Protocol` 拒收 4-str 形态(用 Generic + TypeVar 或 `overload`)
7. 全部 5 子 note 从 `proposed/` 升 `implemented/` 后,根 note 升 `implemented/`,ADR-0178 状态改 `Accepted`

## Risks

- **note 2 需要新 ADR** — `FileSink` fd 语义跨 ADR-0169 L10(命名)+ ADR-0065(账本)的范围,根 note L4 未覆盖。**新 ADR 必须在 note 2 PR 之前 Accepted**(否则 note 2 是悬空提案)。
- **note 4 payload dataclass 与现有 `ExceptionRecord` 的关系** — 是否复用、是否扩展,影响 note 3 的 Protocol 签名。需要在 note 4 PR 描述里**显式声明**。
- **L3 运行时校验性能** — pydantic v2 解析 ~1ms/event,spine 高频 emit 路径(LLM streaming chunks)需白名单豁免。豁免条件在 note 5 lint 守门里定义。
- **5 子 note 跨 4-5 个 PR** — 不强制串行,但**全合后才能升根 note / 改 ADR-0178 状态**。部分合 = 根 note 留在 `proposed/`。

## Open questions

- **note 2 fsync 协议枚举**:`per-write`(DSH 形态,每次 fsync)/ `batch`(LCA 现状,100 条 batch)/ `commit`(close 时一次 fsync)。LCA 应选哪个?默认 batch 但允许 per-write for crash-critical 路径?
- **note 4 用 pydantic v2 还是自建 dataclass + `__post_init__`?** pydantic 重但生态好;自建轻但要重写验证器。倾向 pydantic v2 + selective 复用(只对 boundary EP 强制,高频 chunk path 跳过)。
- **note 5 lint 是扩展 `check_observation_ssot.py` 还是新文件?** 倾向新文件 `check_runtime_invariants.py`(职责清晰:一个是 SSOT 守门,一个是 invariant 守门)。

## Related

### 上游(已完成 + 本根 note 承接)

- [`docs/notes/implemented/seam/2026-09-03-observation-ssot-registry.md`](../../implemented/seam/2026-09-03-observation-ssot-registry.md) — 根 note(PR-1 ~ PR-7 编排)
- [`docs/notes/implemented/contract/2026-09-03-exception-caught-single-emitter.md`](../../implemented/contract/2026-09-03-exception-caught-single-emitter.md) — exception.caught 单 emitter(本 note 3 直接对接)
- [`docs/notes/implemented/contract/2026-09-03-doctor-h-xref-spine-filename.md`](../../implemented/contract/2026-09-03-doctor-h-xref-spine-filename.md) — H-xref 漏读 spine(本 note 1 收尾)
- [`docs/notes/implemented/seam/2026-09-03-model-visible-incomplete-projection.md`](../../implemented/seam/2026-09-03-model-visible-incomplete-projection.md) — model_visible 投影缺三件事(本 note 4 覆盖)
- [`docs/notes/implemented/runbook/2026-09-03-runs-create-wait-hangs-on-completed.md`](../../implemented/runbook/2026-09-03-runs-create-wait-hangs-on-completed.md) — `--wait` 不退出(本 note 1 收尾)

### 同级(本批次 5 子 note)

- note 1 architecture-1-convergence-contract(seam)
- note 2 fsync-semantics(seam)
- note 3 emit-single-entry(seam)
- note 4 payload-schema-typing(contract)
- note 5 runtime-invariants-and-lint(runbook)

### 元决策

- [ADR-0178](../../../adr/0178-observation-control-state-convergence.md)

### 参考

- **DSH(`~/deepseek-harness`)** — 4 级收敛的 TypeScript 实现参考(`SessionEventMap` discriminated union)
- **AGENTS.md §1 / §3 / §5 / §9** — 工程思维、五层单向依赖、Conventions、AGENTS.md 行数约束

---

> **下一步**:用户批准根 note + ADR-0178 后,逐个写 5 子 note。每子 note 落地后单独 PR,根 note 在全部子 note 升 `implemented/` 后再升 `implemented/`。
