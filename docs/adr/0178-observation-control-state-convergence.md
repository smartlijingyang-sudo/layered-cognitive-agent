# ADR-0178: 观测面 / 控制面 / 状态机三方收口 — 四级收敛与单 SSOT 体系

- Status: Proposed
- Date: 2026-09-03
- Supersedes: none
- Depends on:
  - AGENTS.md §1 工程思维(第一性原理 / 总闸 4 问 / 卫生清单)
  - AGENTS.md §3 五层单向依赖 + C1–C7 不变量
  - AGENTS.md §5 Conventions(协议 Protocol 化、命名约束)
  - ADR-0065(可恢复证据账本)
  - ADR-0063(运行事件账本 SSOT)
  - ADR-0165 / 0166 / 0167 / 0167.1(spine 演化)
  - ADR-0169(LoopCursor 控制面)
  - ADR-0175(prompt trace 落 model_visible)
  - ADR-0176(step-tree deriver 闭环 + model_visible dedup)
  - ADR-0177(EnvelopeEmitter binding)
- Scope:
  - `lca/contracts/observability/`(SSOT 注册表扩展)
  - `lca/infrastructure/observability/spine/sinks/`(fd 语义统一)
  - `lca/plugins/observability/spine/reflectors/`(单 emitter 收口)
  - `lca/runtime/{runtime_loop,envelope_emitter,runtime_event_publisher}.py`
  - `lca/agent/{cognitive_agent,team_handle}.py`
  - `lca/contracts/protocols/runtime/envelope_emitter.py`
  - `scripts/check_observation_ssot.py`(既有,扩展 4 级)
  - `docs/notes/proposed/seam/2026-09-03-observation-convergence-root.md`(根 note + 5 子 note)

## 0. 背景与现状痛点(事实)

最近 30 个 commit 全部围绕"观测面 SSOT 收口"。已完成的事实:

| 已落地 | 来源 |
|---|---|
| `lca/contracts/observability/ssot.py` 新增 4 个 helper(`find_spine_file` / `find_exceptions_file` / `find_kernel_log` + `RunLocator` Protocol 扩展) | commit `b9ab222a` 根 note PR-1 |
| `scripts/check_observation_ssot.py` 9 条 lint 规则(SSOT 字面消费方归零) | 同上,PR-2 |
| `to_jsonable` 单一来源(合并 `_capture_io` + `journal/step/projector` 两份) | 同上,PR-3 |
| `RunLifecycleStatus` 上提 contracts(删 `session/session.py:53` 本地 enum) | 同上,PR-3 |
| `seam_key: str` → `CapabilityKey` enum | 同上,PR-7 |
| `FileSink` 接管 exceptions index + `TracingFileSink` fence | commit `9f8aad75` |
| K6 fail-loud traceback SSOT | commit `c60fe433` |
| cursor 是 sole spine EP writer | commit `18184894` |
| `EnvelopeEmitter` Protocol binding | ADR-0177 |

剩余**未收口**的 4 类系统性问题(用户 2026-09-03 提出):

1. **emit 现场混乱** — `runtime_loop.py` 两条 `except` 调 `emit_exception_caught(boundary, exc_type, message, trace_id)`,4 键裸 dict;`reflectors/runtime.py:290` 平行定义同名函数;`EnvelopeEmitter.emit_exception_caught` Protocol 收 4 个 str 而非 `ExceptionRecord`。**3 处入口、3 套签名**。
2. **flush 时机不透明** — `FileSink` 3 套 fd(`<run_id>.spine.jsonl` 主 fd / `<run_id>.exceptions.jsonl` 索引 fd / `TracingFileSink` fallback fd),各自 fsync 策略不同;周期性 batch fsync(100 条 / N ms)只在 `file_sink.py:267` 隐约透露,用户文档缺失。
3. **payload schema 缺失** — `event_descriptor_registry.py` 40 行**只是表**;`payload={...}` 几十处裸 dict,每个 emitter 自填 schema;`exception.caught` payload 缺 `traceback_text` → 4 键 dict < 4 KiB → 不触发 offload → **traceback 永久丢失**。
4. **协议契约乱 + 裸字符串 + 双写** — `RunStatus`(plugin 私有)/ `JournalRunStatus` / `RunLifecycleStatus`(新建)三套并存;`_capture_io.py` + `projector.py` 两份 `to_jsonable` 已合并但下游 reader 还有 alias;`events.jsonl` ↔ `<run_id>.spine.jsonl` legacy 还在;`runtime_loop` 4 键裸 dict vs `lifecycle.py` 走 `exc_to_record` 两条路径并存。

**单一根因**(根 note 已识别):

> **SSOT 已存在,消费方各绕各的**。但仅有"SSOT 收口"不够——需要**4 级收敛**才能消除反复出现的一致性 bug。

## 1. 第一性原理(机制,不是补丁)

**机制是什么**:LCA 的可观测性、控制流、状态机三方各有一套事实表示,**只要任何一方允许"裸字段 / 平行 emitter / 类型化可选",bug 就会从那里长出来**。这是结构性的——靠"修一处 + 加 lint"会无限循环。

**最干净的形态**:**4 级收敛**——一级字符串收口(SSOT) + 二级类型化(payload dataclass) + 三级运行时校验(schema validation) + 四级调用点类型约束(Protocol + Generic)。每一级独立可回滚、每一级独立可观测、每一级独立 delete-when。

**为什么需要 4 级而不是 1 级**:

| 级别 | 解决 | 不解决 | 缺失后果 |
|---|---|---|---|
| 一级 SSOT | 字符串字面收敛 | 字段全不全、类型对不对 | 仍有 schema drift |
| 二级类型化 | payload 必有字段、字段类型固定 | 调用方是否走对入口 | 仍有平行 emitter |
| 三级运行时校验 | 入参不符合 schema 直接抛 | 调用方是否走 Protocol | 仍有"短路 emit"绕过 |
| 四级调用点类型约束 | 编译期拒绝非法签名 | 性能 / 可观测性 | 仍有"看似对但语义错" |

**DSH(参考)做到了 4 级的 3.5 级**:TypeScript discriminated union(`SessionEventMap`)同时承担 二级 + 三级 + 四级。Python 没有静态类型系统,**必须四级分明**才能逼近 DSH 形态。LCA 之前 PR-1 ~ PR-7 只做了一级,这是根 note 反复出现的结构原因。

## 2. 设计(收敛层级与不动范围)

### 2.1 4 级收敛矩阵(本 ADR 范围)

| 级别 | 内容 | 实施位置 | 不动范围 |
|---|---|---|---|
| **L1 SSOT 注册表** | 文件名 / Status enum / Outcome enum / Locator | `contracts/observability/ssot.py`(已建,扩展) | 已有 9 条 lint 不动 |
| **L2 类型化 payload** | 每个 EP 绑定 payload dataclass / TypedDict | `contracts/observability/event_payload_schema.py`(新) | 现有 `ExceptionRecord` 不重构 |
| **L3 运行时校验** | `emit_*` 入口加 `EventPayloadModel.parse_obj(payload)`(pydantic v2 或自建) | `infrastructure/observability/spine/exception_emit.py` + `transport_emit.py` | 性能 < 5% 损耗 |
| **L4 Protocol 签名约束** | `EnvelopeEmitter.emit_exception_caught(record: ExceptionRecord)` 而非 4 str;Protocol 用 Generic `EnvelopeEmitter[T]` | `contracts/protocols/runtime/envelope_emitter.py`(改) | 既有 test 同步迁移 |

### 2.2 三方收口矩阵

| 面 | 当前状态 | 收敛后 |
|---|---|---|
| **观测面** | 5 个并行系统(spine / journal / exceptions index / model_visible / sidecar)各自命名、各自 fd、各自 flush | 1 个 SSOT(L1)+ 1 个 payload schema(L2)+ 1 个 fsync 协议(L3 不在 ADR-0178,在子 note 2)+ 1 个 emit Protocol(L4) |
| **控制面** | `runtime_loop` 直接 `try/except` 调 emit;`EnvelopeEmitter` Protocol 与 `ExceptionRecord` SSOT 类型不一致 | `runtime_loop` 调 `EnvelopeEmitter.emit_exception_caught(record)`;Protocol 与 SSOT 同步 |
| **状态机面** | `RunStatus` × `JournalRunStatus` × `RunLifecycleStatus` 三套并存;`RoleStatus` 字面比较 30+ 处 | `RunLifecycleStatus`(L1)+ `ExecutionOutcome`(L1)+ `CapabilityKey`(L1)统一;字面 grep 归零 |

### 2.3 与现有 ADR 的关系

| 现有 ADR | 本 ADR 影响 |
|---|---|
| ADR-0169 D8–D10(LoopCursor 控制面) | **扩展**:新增"L4 调用点类型约束"对接 `EnvelopeEmitter.emit_*` |
| ADR-0176 D5(H-xref) | **形变**:H-xref 从"5 段 broken detection"降为"spine SSOT 可读性 sanity"(根 note L4) |
| ADR-0177(`EnvelopeEmitter` binding) | **扩展**:把 `emit_exception_caught(boundary, exc_type, message, trace_id)` 4-str 签名改 `emit_exception_caught(record: ExceptionRecord)`,类型与 `ExceptionRecord` SSOT 一致 |
| ADR-0065(可恢复证据账本) | **不动** |
| ADR-0063(运行事件账本 SSOT) | **不动** |
| ADR-0070(Reducer-as-Plugin) | **不动** |
| 老 ADR(`docs/adr/0001-...0177`) | **全部不动**,按 AGENTS.md §1 "老 ADR 全部不动" |

### 2.4 不在本 ADR 范围

| 主题 | 原因 | 真正位置 |
|---|---|---|
| Body 状态机 / SafeExecutor 并发 | 不属于观测 / 控制收口 | 独立 ADR(未提案) |
| Brain / Reasoner / Prompt 拼装 | 同上 | 独立 ADR(未提案) |
| Profile 拓扑变化 | 不属于观测 | ADR-0174 已定义 |
| LobeHub UI 集成 | 不属于 LCA 内核 | deploy 范围 |

## 3. 实施节奏(根 note 编排)

按 5 子 note 顺序,每个 PR 独立可推:

1. **note 1 architecture-1-convergence-contract** — L1 SSOT 收口剩余消费方(根 note PR-3 ~ PR-7 剩余)
2. **note 2 fsync-semantics** — `FileSink` 3 套 fd 统一 fsync 协议,**新 ADR 配套**(根 note L4 不覆盖)
3. **note 3 emit-single-entry** — `runtime_loop` / `reflector` / `EnvelopeEmitter` 3 个 emitter 收口为 1 个 + 删 reflector 平行的 `emit_exception_caught`
4. **note 4 payload-schema-typing** — L2 类型化 + L3 pydantic 校验,L4 Protocol 签名收紧
5. **note 5 runtime-invariants-and-lint** — lint 守门规则扩展至 4 级 + invariant 守门(防回归)

每条子 note 必须自带:
- acceptance criteria(可观察)
- delete-when 条件(任何 compat shim / 平行路径必带)
- 回归锁(test + script)
- 不动范围声明

## 4. 守门(lint + invariant)

扩展 `scripts/check_observation_ssot.py`:

```python
# 一级: 字符串字面
rg '"events\.jsonl"' lca/ scripts/ tests/ → 0(已建)
# 二级: payload 必含字段
rg 'def emit_\w+\(.*payload:\s*dict' lca/ → 0(新增)
# 三级: emit 入口必须 schema 校验
rg 'from .*spine.exception_emit import' lca/ | xargs -I {} rg -L 'pydantic|parse_obj' {} → 0(新增)
# 四级: Protocol 签名不允许裸 str
rg 'def emit_\w+\(.*: str,.*: str\)' lca/contracts/protocols/ → 0(新增)
```

新增 `scripts/check_runtime_invariants.py`:

- `runtime_loop` 必须 `except` 后调 `envelope.emit_exception_caught(exc_to_record(...))`,不允许裸 dict
- `FileSink.__init__` 必须 fsync(parent_dir) on close(POSIX)
- `TracingFileSink` fallback fd 必须自带 fsync-on-write 或 fail-loud

## 5. Delete-when 原则

任何 compat shim / 平行路径 / legacy alias 必须按 AGENTS.md §1 模板填:

```text
# COMPAT(delete-when: <具体条件>, tracking: ADR-0178-<note-id>)
```

具体条件(强制三类之一):
- `<compat> 稳定 ≥ 14 天且无 caller`
- `<compat> 消费者全部迁移完毕(rg 返回零非文档命中)`
- `<compat> 配套新 ADR 已 Accepted 且旧实现零调用`

**无 delete-when 条件的 compat 分支 = 红**:PR 必须补 ADR 或删除。

## 6. 验收(整体)

- 4 级收敛落地后,新加 EP 必须先在 `event_descriptor_registry` 注册 schema;不注册 = lint 失败
- `runtime_loop` 新加 `except` 分支必须走 `exc_to_record`;不写 = lint 失败
- `FileSink` 新加 fd 必须走统一 fsync 协议;不遵守 = lint 失败
- 任何 `emit_*` Protocol 收裸 str 而非类型化记录 = lint 失败
- `docs/notes/proposed/` 5 子 note 全部升 `implemented/` 后,根 note 升 `implemented/`,本 ADR 状态改 `Accepted`

## 7. 工程记录

- AGENTS.md §1"工程思维 · 第一性原理 + 职责单一 + 离开前卫生"全部沿用
- 不写 `try/except Exception: pass`
- 不留没有 ADR / note 的 TODO
- 不为"先让 CI 绿"吞掉 fail-loud
- 离开前跑 `git diff --check`、`ruff check --fix`、`uv run pytest`
- 改动 closure 表(AGENTS.md §1):
  - Protocol / 公共签名(`EnvelopeEmitter.emit_exception_caught` 改 4-str → 1-record):
    同时改实现 + 测试 + ADR-0177 + ADR-0169
  - EP / 词表:`exception.caught` / `exception.finally` / `step.tool_call.record` 等不变 vocabulary
  - Schema / Journal:`event_descriptor_registry` 加 schema 字段,consumer 加迁移
  - 注册表:`RunLifecycleStatus` / `ExecutionOutcome` / `CapabilityKey` 不变,新增 `EventPayloadModel`

## 8. 参考

- **ADR-0063 / 0065** — Journal / Evidence Ledger SSOT
- **ADR-0165 / 0166 / 0167 / 0167.1** — spine 演化
- **ADR-0169** — LoopCursor 控制面
- **ADR-0175** — prompt trace 落 model_visible
- **ADR-0176** — step-tree deriver 闭环 + model_visible dedup
- **ADR-0177** — EnvelopeEmitter binding
- **DSH(`~/deepseek-harness`)** — TypeScript discriminated union `SessionEventMap` 的 4 级收敛参考
- **AGENTS.md §1 / §3** — 工程思维 + 五层单向依赖 + C1–C7

---

> **附**:5 子 note 索引见 [`docs/notes/proposed/seam/2026-09-03-observation-convergence-root.md`](../notes/proposed/seam/2026-09-03-observation-convergence-root.md)。
