# Raphy Assessment — Round 3 (2026-10-07)

**Prompt:** `raphy/prompts/raphy-assess.md`（hardened，2026-10-06）
**Skill:** `skills/improve-codebase-architecture/SKILL.md`（Explore + Present；引用的
`codebase-design`/`grilling`/`domain-modeling` 三个 skill 不存在，按 prompt 内嵌词汇表 + self-grilling 替代）

## Phase 1 — Explore

**YAGNI scoping:** `git log --oneline -60 --name-only -- lca/` 热点计数：
`infrastructure/cli/commands`(12)、`infrastructure/tools/assistant`(11)、
`plugins/transport/webserver`(8)、`infrastructure/cli/services`(8)、
`plugins/composition/composer`(6)、`application/runtime/adapters`(4)、
`plugins/session/*`(多)、`infrastructure/observability/loop_cursor`(3)、
`contracts/observability/cursor`(2)、`cognition/body/executor`(3)。

**禁区排除：** `infrastructure/tools/assistant/` 的命中几乎全是
`memory_tools.py` / `self_manage_tools.py` → ralph Round 2 "MemoryTools directory seam" 领地，
整区避开；`webserver/` 的近期改动是 lca-1000 第 0502–0505 轮退休 stub 删除（活跃 lane 领地），避开；
`cli/commands`、`cli/services`、`composition/composer` 是 RA-004~009 领地，已做完；
`contracts/event.py` 试点 `EventPayload` 分类法是 lca-1000 进行中迁移（注释明示"其余 payload 在后续 PR 补齐"），不重 litigate；
`gate_chain_strategy.py` 动不得（他人未提交工作 + pre-existing 红测试，09:00 轮事故后铁律）。

**最终三区：** session 插件群（`lca/plugins/session/`：`_shared.py`、`projection_registry/`、
`runtime/`、`session_turn_control/` 等）、loop_cursor 包
（`lca/infrastructure/observability/loop_cursor/`：factory、cursor_record、state、
in/、std/、projection/、projections/）、委派缓存 + body 执行器
（`lca/infrastructure/delegation/cache.py`、`lca/loop/commit/delegation_journal.py`、
`lca/cognition/body/executor/simple_body.py`）。

### Friction walk（5 问 × 3 区，逐文件精读）

**A. session 插件群**（`_shared.py` 70 行、`projection_registry/projection_registry.py` 340 行逐行精读）
- Q1 sprawl：无。`ProjectionRegistry` 把注册/引用计数/cell/水位/变更通知收敛在一个 340 行模块里，是 deep module 的正例；理解投影流转只需读这一个文件。
- Q2 浅模块：无。`_shared.py` 的四个 helper（`require_observer_hook`、`TURN_ENDED`、
`session_id_of`、`turn_of`）是 iter-quality 轮收敛的产物，deletion test 全部通过（删掉即回到 4~5 处重复）。
- Q3 locality 缺口：无。`_drive_unit`/`_advance_cell`/`_safe_apply` 与调用方同模块。
- Q4 泄漏：无。只触碰 Session 协议面。
- Q5 盲区：`setup` 声明了 `test_suite="tests/plugins/session/test_projection_registry.py"`，测试面齐。
- **结论：本区无 story。**

**B. loop_cursor**（`factory/factory.py`、`cursor_record.py`、`state/state.py`、
`in/memory.py`、`projection/host.py` 220 行逐行精读）
- Q1：导航摩擦真实存在——`projection/`（单数，`host.py` = StdProjectionHost）
与 `projections/`（复数，`defaults.py` + langfuse/metrics/otel 导出投影）是同级的一字之差模块，
且互相引用（`host.py:26` 运行时 import `projections.defaults`；
`defaults.py:38` 以 TYPE_CHECKING import `projection.host`）。→ **RA-011**
- Q2：StdProjectionHost 本身 deep（锁、disposer token、失败隔离）。`register` 内联 `_dispose`
与 `_do_dispose` 两条 dispose 路径——小瑕疵，未达 story 级。
- Q3：`subscribe_changes` 文档写"订阅 `view_snapshot()` **变化**"，类文档写"**变更**通知"，
但 `drive()` 每次无条件 `_fire_listeners()`（行内注"为简单实现,每次 drive 后全量回调"），
而 `tests/observability/loop_cursor/test_projection_host.py:348` 钉死了按 drive 触发
（"listener should fire on drive"）。三处对"变化"的定义不一致。→ **RA-010**
- Q4：`state/state.py` 的 `_CursorState`/`_snapshot_from_state` 被 `std/std.py`、
`in/memory.py` 跨模块 import 下划线私有名——核查后判定为**刻意**：`state.py:35-40`
文档明示 "internal seam,不进 __all__"，目的是让两 cursor 实现共用投影防漂移；
包内共享非跨层（与 RA-009 的跨层私有访问不同类）。→ dropped，有证据。
- Q5：`CursorRecord` 类级可变 `_cursor` 是 ADR-0185 spec section H 的显式 DI 设计，
有 ADR 背书；`InMemoryLoopCursor(spine=None)` 可选 spine 无害。→ dropped。

**C. 委派缓存 + body 执行器**（`delegation/cache.py` 95 行、`loop/commit/delegation_journal.py`、
`simple_body.py` 383 行逐行精读）
- Q1：一条 cache-hit 要跳 cognition（`action_handlers.py`）→ infrastructure
（`delegation/cache.py`）→ loop（`commit/delegation_journal.py`）+ session bindings，
且后两条边是**函数内局部 import**（`cache.py:59`、`cache.py:77-80`）——层与层的接缝是非正式的。→ **RA-012**（spike 先行，RA-009 同款纪律）
- Q2：`cache.py` 自述 "infrastructure seam (ADR-0194 P1-16)"，单接缝模块，deletion test → 保留。
- Q3：`cached_delegation_observation` 的 todo-38 热路径守卫注释记录了真实裁决
（无 journal 的 raw Session 跳过不抛），不是测试性缺口。
- Q4：双发射（spine fact `team.delegation.cache_hit` + journal `DelegationCacheHit`）——
核查 ADR-0037 Stage 6：journal 是"真值"（控制台投影/cursor 消费），spine fact 供图/追踪，
两边消费者明确，迁移期刻意冗余。→ dropped（lca-1000 领地）。
- Q5：`dispatch_tool_calls` 内联构造 `EffectReceipt` 共 4 次
（`provider="body.dispatch_tool_calls"`、`invocation_id=call.call_id` 重复），
`idempotency_key` 有 3 种形状。→ **RA-013**（本轮唯一的 duplication 类）

**Duplication scan（次要）：** `EffectReceipt(` 跨仓簇在 `infrastructure/computer/fake/`
（sandbox 7、companion 7）和 `machine/adapter.py`（5）——按 YAGNI 是冷区，不追；
`CacheConfig(enabled=False, ttl_s=0)` 全仓仅 `simple_body.py:46` 一处——无簇，dropped。

## Phase 2 — Self-grilling

### RA-010（Worth exploring）：StdProjectionHost 监听触发语义三处不一致
- Constraints：`FlushReport`、`restore()`、`unregister()` 语义不动；ADR-0170 D2 是宿主职责的背书，
但未规定触发粒度——不构成 ADR 冲突。
- Dependencies：调用方 `CloseBarrier`（每次 append 后 drive）；订阅方未知数量——grep 只有测试；
`plugins/session/projection_registry.py` 是兄弟实现（它按 `!=` 变化触发，可作参照）。
- Shape：二选一——(a) change-gated：`drive()` 内比较 `prev_state != new_state` 累积 changed keys，
非空才 `_fire_listeners`；(b) 保持 per-drive：重写两处文档，删掉"变化"承诺。
- Test survival：`test_projection_host.py` 14 个测试；:348 钉住 per-drive——选 (a) 必须改它，
选 (b) 不动它。**新测试**（若选 a）：apply 返回等同状态时 listener 不触发。
- Deletion test："什么算一次变化"的定义收进 `drive()` 一处。✅

### RA-011（Worth exploring）：`projection/` vs `projections/` 一字之差
- Constraints：`StdProjectionHost` 公共面不动；`register_default_exporters` 等导出函数名不动。
- Dependencies：3 处内部 import + `plugins/observability/providers/projection_host/standard.py:38`；
`__init__.py` 的 `__all__` 不变。
- Shape：把 `projections/*` 并入 `projection/`（如 `projection/derivers.py`），或改名
`projections/` → `projection_derivers/`；`defaults.py:38` 的 TYPE_CHECKING import 在合并中重审。
- Test survival：`tests/observability/loop_cursor/` 全目录；grep 旧路径归零。
- Deletion test：不适用（纯导航性）；"投影"概念在包内单点。✅（Worth exploring：纯改名 churn，
但 AI 可导航性是 skill 明示目标。）

### RA-012（Worth exploring）：委派缓存提交接缝契约化（含 spike）
- Constraints：ADR-0194 P1-16 的 seam 归属不动；双发射语义不动；
`DelegationCachePlugin`（`plugins/events/publishers/delegation_cache/plugin.py:52`）是第二调用方。
- Dependencies：`lca.loop.commit.delegation_journal.commit_delegation_cache_hit`、
`lca.infrastructure.session.bindings.active_publish_session/resolve_raw_session`。
- Shape：spike 先读两调用点——若可显式注入，把 commit 函数/会话解析作为参数或小协议传入
`cached_delegation_observation`；若循环 import 真实存在（`lca.loop` ↔ `infrastructure`），
则在模块文档钉死原因 + 测试防回归。
- Test survival：`tests/ -k delegation`；**新测试**：spike 结论若为"循环真实"，加 import 面测试。
- Deletion test：不适用（接缝契约化类，RA-009 同款）。⚠️
- 风险标注：iter lanes 2026-10-07 刚动过 `DelegationCacheHit` 接线——optimize 轮开工前先
`git log` 确认无并发修改。

### RA-013（Worth exploring）：`dispatch_tool_calls` 四处 `EffectReceipt` 收敛
- Constraints：四种 `idempotency_key` 形状逐字保留；`error_code` 字符串不变
（`session_persistence_failed`、`tool_not_registered:*`、`tool_execution_failed`）。
- Dependencies：仅 `simple_body.py` 内部；`EffectReceipt` 契约（`contracts/harness/act/effect_receipt.py`）不动。
- Shape：模块级 `_receipt(call, outcome, error_code=None)`；`provider`/`invocation_id`
在 helper 内单点。
- Test survival：`tests/ -k 'dispatch_tool_calls or simple_body'`；现有测试钉住 receipt 字段。
- Deletion test：收敛——receipt 形状单点，第 5 种错误码不再复制。✅

## Dropped（有证据，不做 story）

| 候选 | 原因 |
|---|---|
| `DelegationCacheHit`（journal）vs `TeamDelegationCacheHit`（新 `EventPayload` 试点）收敛 | lca-1000 进行中迁移；`contracts/event.py:397` 明示"其余 payload 在后续 PR 补齐"。raphy 不重 litigate 活跃迁移。 |
| `_snapshot_from_state`/`_CursorState` 跨模块私有 import | 包内刻意 internal seam（`state.py:35-40` 文档），防两 cursor 实现漂移；与 RA-009 的跨层私有访问不同类。 |
| `CursorRecord` 类级可变 `_cursor` | ADR-0185 spec section H 的显式 DI 设计，有 ADR 背书；删掉是搬运。 |
| 双发射（spine fact + journal `DelegationCacheHit`） | ADR-0037 Stage 6 刻意设计，两边消费者明确。 |
| `CacheConfig(enabled=False)` 收敛 | 全仓仅一处，无簇。 |
| `LoopCursorFactory.from_profile` 文档漂移（Parameters 写 plan_ref"可有可无，缺省 'default'"，实现却是 fail-loud TypeError） | 一行文档修复，hygiene 级，不够 story；记入未来 hygiene 轮。 |

## Phase 3 — Present

| ID | Files | Problem（friction） | Solution | Benefits（locality / leverage） | Strength |
|---|---|---|---|---|---|
| RA-010 | `loop_cursor/projection/host.py`、`tests/.../test_projection_host.py` | 文档承诺"变化通知"，实现每次 drive 全量回调，测试钉死 per-drive——三处对"变化"定义不一致 | 二选一落定：change-gated（drive 内算 changed keys）或保持 per-drive 改文档；实现/文档/测试三方对齐 | "什么算变化"单点决策；订阅方可信赖契约 | **Worth exploring** |
| RA-011 | `loop_cursor/projection/` vs `projections/` | 同级一字之差两模块互引，导航/AI 可读性摩擦 | 并入 `projection/` 或改名；3+1 处 import 更新 | 投影概念包内单点；未来 agent 不再走错 | **Worth exploring** |
| RA-012 | `infrastructure/delegation/cache.py` | 到 loop 层与 session 层的边是函数内局部 import，非正式接缝 | spike：显式注入 commit 接缝；不可行则文档+测试钉死循环原因 | 层边诚实；commit 路径可经 interface 测试 | **Worth exploring** |
| RA-013 | `cognition/body/executor/simple_body.py` | `dispatch_tool_calls` 内联构造 `EffectReceipt` 4 次 | 模块级 `_receipt` helper 收敛 | receipt 形状单点；新错误码不再复制 | **Worth exploring** |

**Top recommendation:** RA-010 first。契约歧义类（文档/实现/测试三方打架）是真实的维护风险；
blast radius 小（单模块 + 单测试文件）；验收机械可验证（三方对齐）。其次 RA-011
（纯改名，零行为风险，导航收益立竿见影）。

**Diversity quota:** 4 个故事中 3 个来自 friction walk
（RA-010 语义歧义、RA-011 命名/导航、RA-012 接缝契约化），仅 RA-013 为 duplication 类。✅

**Stories written:** RA-010（P1）、RA-011（P2）、RA-012（P3）、RA-013（P4），`passes: false`，
接 RA-001~009 续号。分支：`raphy/arch-20261007-0930`。

**Learnings for future iterations:**
- loop_cursor 包内 `projection/`（宿主）vs `projections/`（定义）的一字之差是真实导航税；
看到单复数并存的同级模块先怀疑。
- `_fire_listeners` 的"为简单实现"注释 + 测试钉死 per-drive：当测试把"简化实现"钉成契约时，
文档里的"变化"承诺就成了负债——三方对齐本身就是 story。
- 包内共享私有实现（`_snapshot_from_state`）有文档背书时是健康的 internal seam；
RA-009 的教训只适用于跨层私有访问，不要泛化打击。
- 试点中的新事件分类法（`contracts/event.py` PILOT）是 lca-1000 领地：看到"后续 PR 补齐"
字样就收手，不开 competing story。

Assessment complete: 4 stories written, top is RA-010.
