# Raphy Assessment — Round 6 (2026-10-07 23:15, branch `raphy/arch-20261007-2315`)

ASSESS ONLY. 本轮按硬化版 `raphy-assess.md` 执行：读 `skills/improve-codebase-architecture/SKILL.md`
→ git log 热点定域 → 三区 friction walk（5 问必答，端到端精读非 grep）→ duplication 副扫描
→ self-grilling → stories 入 prd.json（`userStories` 键，RA-019 起编号）。

## Scope（YAGNI）

`git log --oneline -70` 生产代码热点（排除已做故事领地 + 纯测试文件 + 禁区）：
- `lca/infrastructure/host_runtime/providers/user_cli.py` ×6 → RA-014/015 已做，避开
- `lca/infrastructure/cli/services/daemon/daemon.py` ×6 → RA-014 已做，避开
- `lca/infrastructure/cli/commands/_shared/projection.py` ×5 → CLI 刻意规则 + projection 已收敛，避开
- `lca/plugins/session/_shared.py` ×3 / `projection_cache.py` ×3 → session 插件群热
- `lca/plugins/assistant/tool/overlay.py` ×2 / `jobs.py` ×2 / `evolve.py` ×2 / `events/_events.py` ×2 → assistant 插件群热
- `lca/infrastructure/sandbox/runtime/runtime.py` ×2 → 新鲜热区，无 raphy 历史

禁区遵守（`raphy/progress.txt` 顶部 `## Codebase Patterns`）：ralph Round 2 领地、
lca-1000 领地（`contracts/event.py` PILOT + `plugins/transport/webserver/`）、
iter lanes 的 DelegationCacheHit 接线区、`gate_chain_strategy.py`（绝不动）、
`lca/cognition/memory/`、MemoryTools（`infrastructure/tools/assistant/`）、
RA-016~018 刚做的 source_verify / session catalog / tool_defer。三区全部避开。

选定三区：**A. `lca/plugins/session/`**（_shared / projection_cache /
telemetry_capture / session_turn_outline / session_stats / title_service /
spine_anomaly 全文）**B. `lca/plugins/assistant/`**（events/_events /
tool/overlay / jobs / evolve 全文）**C. `lca/infrastructure/sandbox/runtime/`**
（runtime.py + scope.py 全文）。

## Friction walk

### 区 A — session 插件群（_shared 系）

**Q1. 理解一个概念要在多少小模块间跳？** 理解"一个 session 插件如何把
observer 挂到 SessionStore"要在 5 个文件间跳：projection_cache、
telemetry_capture、title_service、spine_anomaly、projection_registry 各自写
了一遍"遍历 `store.list()` 逐个挂入（含 contained）→ `require_observer_hook`
fail-loud → `hook` 接管未来 create/restore → cancel 存 `_store_hooks`"。
语义是同一 ritual，只是挂入体不同（`register_to` / `_observe_contained`+
游标播种 / `_TitleObserver` / 异常 observer）。→ **RA-019 候选**。

**Q2. 哪些模块浅？（deletion test）** `_shared.py` 目前 52 行：`TURN_ENDED`
常量、`require_observer_hook`、`session_id_of`、`turn_of`——四个都是具名
收敛产物，删除任一都会把知识散回 5 个插件文件 → 集中了复杂度，
earns existence。但它只收敛了"件"，没收敛"仪式"（attach ritual）——
deletion test 反问：把 attach ritual 删了（不收敛）复杂度去哪？
答案：继续散在 5 处，顺序还分两派（见 RA-019 notes）。→ 收敛有收益。

**Q3. 纯函数抽出但 bug 藏在调用处？** telemetry_capture 的
`_seed_telemetry_cursor` 读 `header.is_seeded` / `seed_length` 做游标播种：
纯函数式 helper，但"播种时机"（只在 attach 时）藏在 `_observe_contained`
里——不过这是刻意设计（播种只发生在挂入时刻），且有 `reset_handoff_cursor`
显式接缝。→ 不开 story。

**Q4. 紧耦合跨接缝泄漏？** `session_turn_outline.py` / `session_stats.py` 各
手写 `"turn.started.v1"` / `"step.started.v1"` / `"message.accepted.v1"`
字面量（turn_outline 3 个、stats 3 个），与 RA-017 收敛的 DSH surface 词表同类
问题。但 `lca/session/catalog.py` 的 `known_session_event_types()` 是否已
覆盖这些 turn/step/message 类型？若 catalog 闭集包含，RA-017 idiom 可延伸；
若不包含（turn/step/message 是 kernel session 词表而非 session 包词表），
强行 single source 会造成错的家。快速核查：catalog 是 DSH 对齐的 session
surface 词表，turn.started 这类属 `lca_kernel.events.session.session`
的 kernel 词表——RA-017 的 `surface_types.py` 放 session 包是经过层向论证的，
把 kernel 词表再收一遍属于"注释自称 single source"的反模式（Round 4
learnings）。→ **有证据丢弃**。

**Q5. 测试面？** `tests/plugins/session/` 有 5 插件各自的测试（attach ritual
被 `test_title_service.py` / `test_spine_anomaly_observer.py` 等覆盖）。
"接口即测试面"成立：`register_to` / `observe_session` / `attach_to_store`
都是公开面。→ 无测试面 gap。

### 区 B — assistant 插件群

**Q1. 跳模块？** 理解"助理配置面变更"要跳 tool/overlay.py（`_write` /
`remove` / `_build_manifest`）+ skill/overlay/overlay.py（同构 ritual）+
`home/_home_layout.py`（`build_manifest`/`write_manifest`/
`write_revision_snapshot`）。tool 与 skill 的 manifest 修订仪式形状高度同构
（load → revision+1 → build → section 拷贝/变异 → write → snapshot →
profile.revised EP），差异在 digest 前缀（`tools/` vs `skills/`）与 section
条目形状——ADR-0243 D2 明确这是"同构"设计。把整仪式收敛会参数化出一个
四不像；但 `_revision_of` 已经是两份字节级相同（tool/overlay.py 私有 vs
skill/overlay/gating.py 包内共享，经 `__init__` 再导出）。→ 只有
`_revision_of` 是干净的收敛点，但它已被 skill 侧收敛过一次、且只剩 2 处、
7 行函数——"one adapter = hypothetical seam" 警戒线：两处且语义逐字相同，
勉强算 real，但杠杆太小。→ **有证据降级为观察，不开 story**
（若第三处出现再开）。

**Q2. 浅模块？** `events/_events.py`：9 个 frozen dataclass payload，
每个重复"4 必含字段声明 + `__post_init__` 调 `_validate_required_fields`
+ `to_dict` = `_required_dict` + truthy extras"。逐个看都不浅（每个有自己的
extra 校验语义），但作为"族"它们共享同一形状知识。Deletion test：删掉一个
假想的 base → 形状知识散回 9 处；ADR-0187 的 12-EP 闭集意味着第 10 个
payload 还会再抄一遍。→ **RA-022 候选**（族级 shallow）。

**Q3. bug 藏在调用处？** `jobs.py` 的 `fire()`：`message=registered_item.message
if registered_item is not None else ""`。`plane.get` 是 Protocol（返回
`WorkItem | None`），本地 register 成功 ⇒ `submit()` 已成功 ⇒
`get` 返回 None 意味着队列丢了该 item——此时 fire 照发，prompt 为空串，
但 `assistant.job.fired` EP 照发。fail-closed 设计（本文件 docstring 通篇）
在这里 fail-open。→ **RA-021 候选**。

**Q4. 泄漏？** overlay.py 的 `_iso` / `_revision_of` / `_tool_dir` 等模块私有
helper 都是文件内聚，无跨接缝泄漏。`emit_assistant_ep_or_log` 已是收敛产物。
→ 无。

**Q5. 测试面？** `tests/plugins/assistant/test_jobs.py`、`test_tool_overlay.py`、
`test_catalog.py`（覆盖 EP payload to_dict）存在。RA-021 的空 message
分支是否有测试钉住？grep 未见——这正是故事验收要求新测试的原因。

### 区 C — sandbox runtime

**Q1. 跳模块？** 理解"一次 run 的沙箱生命周期"主要在 runtime.py
（530 行）内：`ensure_ready`（mount→verify→inspect→baseline）→
`execute`/`run_terminal` → `destroy`。`scope.py` 只做 run_id 注册表。
单文件内聚，depth 好。→ 无 sprawl。

**Q2. 浅模块？** 模块级小函数 `_office_flush_cmd`、`_append_artifact_scanner`、
`_file_fingerprint` 都是真 helper（被多处调用、语义单一），deletion test
通过。→ 无。

**Q3. bug 藏在调用处？** `destroy()` 只重置 `_session=None`、`_ready=False`，
不碰 `_stateless`。初看像"destroy 后永久 stateless" bug——但查
`scope.py:unbind_sandbox_runtime`：runtime 先从注册表 `pop` 再 `destroy`，
被 destroy 的实例永不复用 → 该分支生产不可达。→ **有证据丢弃**
（self-grilling 否决；已记入 progress.txt Codebase Patterns 防后人重提）。

**Q4. 泄漏？** `_run_inspect_internal` 内两处函数级 import：
`from lca.infrastructure.skills.format.routing import enrich_inspect_profile`
和 `from lca.infrastructure.workspace import get_run_workspace`。
RA-009/RA-012 纪律：deferred import guilty-until-proven-innocent。
本轮做了 fresh-interpreter 探针（routing-first / runtime-first / workspace
三种顺序）：全部干净加载，无 import cycle——"没有 cycle 在躲"，
假设被证据证伪（RA-009 class）。→ **RA-020 候选**。

**Q5. 测试面？** `tests/infrastructure/sandbox/` 存在；`_run_inspect_internal`
的 enrich 步骤走公开面可测。→ 无 gap。

## Duplication 副扫描

- `require_observer_hook` 5 处调用 → 已是收敛产物（_shared），不重复开。
- `_attach_to_store` ritual 5 处 → 即 RA-019（主扫描已覆盖）。
- `_revision_of` 2 处字节级相同 → 杠杆不足，观察（见区 B Q1）。
- EP payload `__post_init__`/`to_dict` 9 处 → 即 RA-022。
- `_TURN_ENDED` / `_validate_required_fields` 等 → 已收敛，不重复。

## 候选表

| ID | Files | Problem | Solution | Benefits（locality+leverage）/ 测试 | Strength |
|---|---|---|---|---|---|
| RA-019 | `lca/plugins/session/_shared.py` + 5 插件 attach 点 | 5 个 session 插件各写一遍 store-observer attach ritual（list 遍历含 contained → require_observer_hook fail-loud → hook 接管未来 → cancel 存 `_store_hooks`），且顺序分两派（title_service require-first，其余 list-first） | ritual 收敛进 `_shared.attach_store_observers(store, attach_one, hooks_sink)`；统一 canonical 顺序并记录 delta | locality：attach 契约单点；leverage：未来第 6 个 session 插件直接复用；测试：5 插件现有测试钉住语义 | Worth exploring |
| RA-020 | `lca/infrastructure/sandbox/runtime/runtime.py` | `_run_inspect_internal` 函数级 import 藏层边（RA-009/RA-012 同款）；探针已证无 cycle | 提升到模块顶层 import，层边诚实化 | locality：依赖在文件头一目了然；leverage：后人不再误判"这里有 cycle"；测试：import 顺序探针 + 现有 sandbox 测试 | Worth exploring |
| RA-021 | `lca/plugins/assistant/jobs/jobs.py` | `fire()` 在 `plane.get` 返回 None 时静默发空 prompt 的 WorkItem，违背本插件 fail-closed 设计 | 先 probe 真实 0093 `get` 语义：不可达则删分支改 fail-loud；可达则显式决策（log+拒收或文档化） | locality：fail-closed 语义无例外；leverage：fire 路径的错误契约钉死；测试：新增恢复缺失分支测试 | Worth exploring |
| RA-022 | `lca/plugins/assistant/events/_events.py` | 9 个 EP payload dataclass 各抄一遍"必含四字段 + `__post_init__` 门 + `to_dict`" | 抽 frozen dataclass base：quartet 字段 + base `__post_init__`（调 `_validate_required_fields` + `_validate_extra_fields` hook）+ base `to_dict`（`_required_dict` + `_extra_items()` 接缝） | locality：payload 形状规则单点；leverage：ADR-0187 12-EP 闭集后续 payload 零拷贝；测试：to_dict 字节等价（golden）+ 现有测试 | Worth exploring |

## Self-grilling（逐候选，写在 assessment 里）

**RA-019**
- Constraints：fail-loud（缺钩子抛 TypeError）与 fail-soft（单 session 挂入失败
  contained）语义必须逐字保留——这是 DSH 对齐的文档化选择；`spine_anomaly`
  不存 cancel（无 `_store_hooks`），收敛后 `hooks_sink` 参数可选。
- Dependencies：调用方是 5 个插件的 setup/attach 路径；被挂的是
  `Session.observe` / `SessionStore.add_observer_hook` / `list()`。
- Shape：`_shared.attach_store_observers(store, attach_one, hooks_sink=None)`；
  `attach_one(session)` 由各插件提供（含各自的 contained 日志 scope）。
- Test survival：`tests/plugins/session/test_title_service.py`、
  `test_spine_anomaly_observer.py` 等钉住 attach 行为；新增测试钉住
  canonical 顺序（require-first vs list-first 二选一）。
- Deletion test：concentrates——删掉它，5 处 ritual + 顺序分歧散回去。

**RA-020**
- Constraints：`enrich_inspect_profile` 与 `get_run_workspace` 的调用语义不变；
  只是 import 位置上移。
- Dependencies：`lca.infrastructure.skills.format.routing`（→ bundled →
  disk/frontmatter）、`lca.infrastructure.workspace`（→ scope/persistent_workspace）。
- Shape：模块顶层两行 import；删掉函数内的延迟 import。
- Test survival：现有 `tests/infrastructure/sandbox/` 钉住 inspect 行为；
  探针本身（三种顺序 fresh-interpreter 加载）可固化为测试或文档。
- Deletion test：concentrates——层边知识从"藏在函数里"变成"写在文件头"。
- 反问"这是不是假问题"：探针已证无 cycle，延迟 import 无存在理由；
  唯一的代价是 runtime.py import 时多拉 skills.format.routing——可接受，
  且与 codebase"层边诚实"纪律一致。

**RA-021**
- Constraints：ADR-0187 §3 D10 fail-closed；跨进程恢复（deterministic work_id）
  必须继续工作；`assistant.job.fired` EP 的 12-EP 闭集语义不变。
- Dependencies：`ContinuousControlPlane.get`（Protocol，返回 Optional）；
  真实实现是 0093 WorkQueue——probe 必须读真实实现，不是 Protocol。
- Shape：两种可能结局——(a) 不可达：删 `else ""`，恢复缺失时抛
  `JobNotRegisteredError`；(b) 可达（如队列 evict）：显式 fail-loud 或
  有日志的显式决策。二选一，证据写进 commit。
- Test survival：`tests/plugins/assistant/test_jobs.py` 现有 fire 测试；
  新增恢复缺失分支测试。
- 反问"这是不是假问题"：`plane.get` 的 Optional 返回是契约的一部分，
  不是防御性编程——分支可达性未知才需要 probe，而不是已知不可达。
  若 probe 证实真实实现永不返回 None，故事退化为"删死代码"，依然成立。

**RA-022**
- Constraints：ADR-0187 §3 D8/D9 payload 闭集（只含元数据）；`__post_init__`
  保持 fail-loud；`to_dict` 输出形状字节等价。
- Dependencies：调用方是各插件的 `_emit_*`（经 `emit_assistant_ep_or_log`）；
  测试 `test_catalog.py` 钉住部分 payload 行为。
- Shape：`_AssistantEPPayloadBase`（frozen dataclass）：4 必含字段 +
  `__post_init__`（`_validate_required_fields(self, type(self).__name__)` +
  `self._validate_extra_fields()` hook）+ `to_dict`
 （`_required_dict(self)` + `self._extra_items()`）；子类只声明 extra
  字段 + `_validate_extra_fields` + `_extra_items`。
- Test survival：现有 catalog/EP 测试；新增 golden-dict 对比（9 个 payload
  的 to_dict 改前改后一致）。
- Deletion test：concentrates——"必含四件套 + truthy extras 进 payload"
  规则从 9 处收进 1 处。
- 反问"这是不是假问题"：9 处是真簇（非 2 处 hypothetical），且 ADR-0187
  12-EP 闭集还有 3 个 EP 未落 payload 类（`assistant.created` 等已在类列表里…
  实际 9 类已覆盖 8 个 EP 名，闭集内新增 payload 仍需抄）——拷贝成本是
  recurring 的。

## 丢弃（有证据）

1. 区 A Q4：turn/step/message kernel 事件字面量 single source——`lca_kernel`
   词表与 session 包词表是两个命名空间，RA-017 的层向论证不适用；强行收敛
   是"注释自称 single source"反模式（Round 4 learnings）。
2. 区 B Q1：`_revision_of` tool/skill 两份——只剩 2 处 7 行，杠杆不足；
   第三处出现再开。
3. 区 C Q3：`destroy()` 不重置 `_stateless`——`unbind_sandbox_runtime` 先
   pop 再 destroy，被 destroy 的实例永不复用，生产不可达；测试直调
   destroy 的是 teardown 路径。误报，已记 Codebase Patterns。
4. tool/skill overlay 整仪式收敛——ADR-0243 D2 同构是刻意设计，digest
   前缀与 section 条目形状差异是本质差异，收敛会参数化出四不像。

## Diversity quota

4 个故事：2 friction（RA-020 seam 诚实、RA-021 fail-closed 缺口）+
2 duplication（RA-019 5 处 ritual、RA-022 9 处 payload）。非全 duplication，
满足 quota；且两个 friction 都来自 friction walk 的 Q3/Q4（非 grep 发现）。

## Top recommendation

先做 **RA-019**：5 处 ritual 是本轮最大的真实簇，且顺序分歧（require-first
vs list-first）是语义级差异——现在不统一，第六个插件抄的时候必抄错一边。
其次 **RA-021**：fail-closed 缺口是唯一"可能静默做错事"的候选，probe
成本低（读一个实现），结论二选一都很干净。RA-020 是纯机械提升，
RA-022 是族级收敛，可依次做。

Assessment complete: 4 stories written, top is RA-019.
