# Raphy Assessment — Round 5 (2026-10-07 20:05, branch `raphy/arch-20261007-2005`)

ASSESS ONLY. 本轮按硬化版 `raphy-assess.md` 执行：读 `skills/improve-codebase-architecture/SKILL.md`
→ git log 热点定域 → 三区 friction walk（5 问必答，端到端精读非 grep）→ duplication 副扫描
→ self-grilling → stories 入 prd.json（`userStories` 键，RA-016 起编号）。

## Scope（YAGNI）

`git log --oneline -80` 热点（排除已做故事领地 + iter style 扫荡 + 纯测试文件）：
- `lca/infrastructure/host_runtime/providers/user_cli.py` ×6 → RA-014/015 已做，避开
- `lca/infrastructure/cli/services/daemon/daemon.py` ×5 → RA-014 已做，避开
- `lca/infrastructure/observability/loop_cursor/...` → RA-010/011 已做，避开
- `lca/infrastructure/delegation/cache.py` ×2 → RA-012 已做，避开
- `tests/scenario/*` 大量测试文件（scenario 族测试活跃，但 lca/ 生产侧无对应热点 → 测试侧热）
- 剩余生产代码热点：`lca/session/catalog.py`（session 事件类型闭集）、
  `lca/infrastructure/source_verify/*`（2026-10-02 落地，README 明确列了"后续（未做）"）、
  `lca/infrastructure/tool_defer/*`（2026-10-01 落地）

禁区遵守（`raphy/progress.txt` 顶部 `## Codebase Patterns`）：ralph Round 2 领地、
lca-1000 领地（`contracts/event.py` PILOT + `plugins/transport/webserver/`）、
iter lanes 的 DelegationCacheHit 接线区、`gate_chain_strategy.py`（绝不动）、
`lca/cognition/memory/`、MemoryTools（`infrastructure/tools/assistant/`）。
三区全部避开。

选定三区：**A. `lca/infrastructure/source_verify/`**（verifier/claims/policy/registry/__init__ 全文）、
**B. `lca/infrastructure/tool_defer/`**（session/policy/tool_search/__init__ 全文）、
**C. `lca/session/`**（__init__/append/catalog/fold 全文；lifecycle 只读目录清单与导出表，
bind/checkpoint/recovery/repair 是各自独立的生命周期 concern，不重复精读）。

## Friction walk

### 区 A — source_verify（ProvenanceGuard 思想落地）

**Q1. 理解一个概念要在多少小模块间跳？**
理解"一条断言的裁决"要跳 verifier.py（`_judge_claim`）+ claims.py（切分/引用提取）+
registry.py（登记/查回）+ policy.py（VerifyPolicy）+ `contracts/models/cognition/source_verify.py`
（ClaimVerdict 等契约）。5 个模块，但每文件顶部 docstring 把自己在 ProvenanceGuard
流水线里的位置写明（"三件事" / "启发式实现" / "介入强度" / "登记簿"），README.md 有三件套
机制说明 + 缝合点（采集在 `execute.py::_append_tool_result_surface`、校验建议接 delivery_synth）。
是**文档化的刻意分离**，非 sprawl。→ 不开 story。

**Q2. 哪些模块 shallow？**
policy.py（31 行，VerifyPolicy frozen dataclass + 3 个 classmethod）interface≈implementation。
但它是纯配置 switchboard（OFF/WARN/ENFORCE 三种 run 姿态命名）；deletion test：
删掉会把模式开关散进 verifier 的调用方 → concentrates，通过，保留。→ 不开 story。

**Q3. 为可测性抽出的纯函数，bug 藏在调用处？**
`_extract_literals`（verifier.py）是模块级纯函数 + 模块私有 `_LITERAL` 正则——它是
**实际决定 verdict 的文法**（哪些字面量算"可核验"：日期/数字/标识符三分支），
但没有任何接缝：改文法必须改 verifier.py 内部；调用方不能注入；NLI 未来是预留缝
（docstring 明说），但**当前实际生效的字面文法反而没有缝**。claims.py 的
split_claims/extract_citations 已是具名导出函数（`__init__` 导出），唯独 verdict 核心的
文法是匿名的。→ **产出 RA-016**。

**Q4. 紧耦合模块的 seam 泄漏？**
`ensure_registry` 用 `_lca_source_registry` 私有属性名挂到无类型 runtime 上
（legacy harness 兜底）——docstring 明示"取不到就返回临时 registry"，是刻意的 fail-soft，
非泄漏。`SourceVerifier.verify` 拿具体类 `SourceRegistry` 而非 protocol——但 verify 本身
尚无生产调用方（README"建议接 delivery_synth.py"未落地），现在换 protocol 无收益。
→ 不开 story（记 observation）。

**Q5. 哪些部分测不到 / 只能绕过 interface 测？**
文法（三分支正则）只能经完整 `verify()` + 伪造 registry 内容测——"interface 即 test surface"
的反例：想钉"标识符最短 4 字符"这类文法行为，必须走整条流水线。测试现状：
`tests/infrastructure/source_verify/test_source_verify.py` 存在（钉住流水线行为），
但文法无独立 test surface。→ 并入 RA-016。

**区 A 结论**：产出 RA-016（Worth exploring）。附带 observation：`verify_final_answer`
尚无生产调用方（采集已接 `execute.py:271`，校验未接）——这是接线 gap，不是架构
deepening，不开 story。

### 区 B — tool_defer（Muse L1 对齐）

**Q1.** 理解"defer 一轮"要跳 session.py（ContextVar seam、`update_turn`、`render_turn`）+
policy.py（DeferPolicy）+ tool_search.py（loader tool）+ `concept.tool.fork/dispatch.py`
（每 turn 刷新）+ `think.history.assemble`（模型可见投影）。session.py 模块 docstring
把生命周期与三个缝合点逐一名出（"mirroring current_tools_service"、
"never rebuilt inside dispatch"），是文档化的编排。→ 不开 story。

**Q2.** policy.py 纯配置（STANDARD_NAMESPACES/描述表/eager 集合 + for_vocal_mode）；
tool_search.py 的 ToolSearchTool 是 thin adapter（args→session 调用 + Observation 包装，
failure_kind 分类引 `docs/specs/tool-failure-recovery.md` §3）。deletion test：
删 adapter 会把模型参数翻译散进 session/dispatch → concentrates，保留。→ 不开 story。

**Q3.** `search_catalog` 的 token 匹配+排序启发式（约 45 行纯逻辑）嵌在 347 行的
stateful ToolDeferSession 里——但它操作的正是 session 自己的状态（_namespaces/_specs），
locality 对；interface 路径（update_turn→search_catalog）就是它的 test surface，
`tests/infrastructure/tool_defer/` 有 8+ 测试文件钉住。→ 不开 story。

**Q4.** `render_turn` 的 eager_present deadlock 兜底（"catalog 指向缺失的 tool_search
是死锁"）是 dispatch 级知识——但注释明示刻意（loader 必须在 wire 上），属 fail-safe
设计。`_tool_to_spec` 与 `think.history.assemble._tool_to_spec` 两份 wire shape——
**刻意**（注释："Kept local on purpose: infrastructure must not import L2 nodes"），
"one adapter = hypothetical seam" 的反面证据：这里连第二个 adapter 都不该有。
→ 不开 story。

**Q5.** ToolSearchTool.execute 依赖 ContextVar 绑定（无绑定时返回 validation failure
observation 而非抛错）——session.py 提供 set/reset seam，tool_defer 测试全覆盖。
`_describe` 的 ValueError fail-fast vs `update_turn` 的 fail-soft "unknown" 停靠——
ADR-0256 B2 背书的刻意双轨。→ 不开 story。

**区 B 结论**：无 friction，不开 story（读了 5 文件，问题均不适用或有刻意设计证据）。

### 区 C — lca/session（Fact plane，ADR-0195）

**Q1.** 理解"一次 append"：append.py 的 Session 类自包含（452 行，时序契约 4 步 +
flush 链 ADR-0186 全写在类 docstring）。但 `derive_messages()` 方法内**函数级 import**
`lca.plugins.session.runtime.projection.reader`——投影 fabric 的接线在模块级不可见，
是隐藏 seam。查原因：plugin 层依赖 session 层，反向顶层 import 会成环 → 刻意的延迟绑定。
→ 不开 story（有证据的刻意）。

**Q2.** catalog.py（45 行）：`known_session_event_types()` 把 4 个词表
（`event_registry()` + SURFACE_EVENT_TYPES + SPINE_EXECUTION_POINTS +
SPINE_EVENT_CATEGORIES，来自 3 个包）取并集 + **1 个硬编码字面量**
`"surface/developer_message"`（ADR-0268 §6 DSH 对齐）。deletion test：删 catalog
会把"type 闭集"散到各读路径 → concentrates，通过保留。但 4 个词表是*派生*的
（源头长大自动跟进），第 5 个是*手工*的（源头变了要人记着改这里）。
→ **产出 RA-017**。

**Q3.** `_to_jsonable` / `_estimate_size` / `_validate_json_safe` / `_snapshot_data`
四个纯 helper 全在 append.py 内使用处旁边，locality 好。4 遍树遍历是 2026-09-16
stall postmortem 后的刻意性能取舍（注释写明），非"为可测性抽取"。→ 不开 story。

**Q4.** append.py 顶层 import `lca_kernel.events.session.session` 的 SessionEvent/
SessionHeader——lca 层直引 kernel 类型。查架构：lca/session 是 Fact plane
（ADR-0195），kernel 是 vendored 下层；fold.py 的 re-export 是刻意 internal seam
（防两实现漂移，同 `_snapshot_from_state` 模式）。无泄漏证据。→ 不开 story。

**Q5.** `validate_event_type_for_read` 读路径 fail-closed，有
`tests/observability/session/test_known_types_fail_closed.py` 钉住；
`_attach_projection_registry(registry: Any)` 未类型化 setter——小瑕疵，
不值得单独开 story。

**区 C 结论**：产出 RA-017（Worth exploring）。

## Duplication 副扫描（friction walk 之后）

- `ToolSearchTool.execute` 与 `validate` 各算一遍 `has_ns` / `has_nss` / `has_query`
  （tool_search.py，同模块内约 6 行机械重复）。且两处分类器**口径不一致**：
  execute 的 has_nss 只判 `isinstance(list)`，validate 的要求非空 list 且元素非空
  （execute 实际走不到分歧分支——validate 先拦，但"两个真值"本身就是坏味道）。
  收敛为一个 `_classify_args` helper。→ 产出 RA-018（duplication 类）。
- 丢弃：`_tool_to_spec` ×2（刻意，注释背书）；append.py 内两个
  `contextlib.suppress(ValueError)` 取消 idiom（3 行，无行为面）；
  `_estimate_size` 与 `_to_jsonable` 的双遍历（刻意性能取舍）；
  `registry.get()` 的 None 处理两处（trivial）。

## 候选表

| # | Files | Problem | Solution | Benefits（locality+leverage） | Strength |
|---|-------|---------|----------|-------------------------------|----------|
| RA-016 | `lca/infrastructure/source_verify/verifier.py` | 实际决定 verdict 的字面量文法（`_LITERAL` 三分支 + `_extract_literals`）是 verifier.py 的模块私有物：无具名接缝、无独立 test surface；改文法必须改 verifier 内部，调用方不可注入；NLI 有预留缝，当前实际生效的文法反而没有 | 把字面量抽取收敛为 `SourceVerifier` 可注入的 seam（protocol/构造参数，默认=现有正则文法）；verifier 只经 seam 拿 literals | locality：文法演化（中文日期形态、新标识符形状）不再碰 verdict 判定逻辑；leverage：后续接 NLI 或领域文法时替换一处；测试：文法可独立于 registry/verify 流水线被钉住 | Worth exploring |
| RA-017 | `lca/session/catalog.py`（+ DSH surface 词表源头） | `known_session_event_types()` 是 4 个派生词表 + 1 个手工字面量 `"surface/developer_message"` 的并集；前者随源头自动长大，后者靠人记着改——读路径 fail-closed 的保证有一处手工单点 | 把 DSH surface 词表定义为具名常量（与 `SURFACE_EVENT_TYPES` 并列的 single source），catalog 只做并集，零手工字面量 | locality："session 认识哪些 event type"完全派生，无人肉同步点；leverage：DSH 词表再长大时 catalog 零改动；测试：fail-closed 测试继续钉住闭集 | Worth exploring |
| RA-018 | `lca/infrastructure/tool_defer/tool_search.py` | `execute` 与 `validate` 各自实现一遍参数分类（`has_ns`/`has_nss`/`has_query`），口径还不一致（execute 的 has_nss 不判非空）——"两个真值"的坏味道 | 收敛为单个 `_classify_args(args)` helper，两处共用同一口径（取 validate 的严格口径） | locality：参数形状的判定只活在一处；leverage：加新参数模式时改一处；测试：分类器可直接单测 | Worth exploring |

## Self-grilling

### RA-016
- **Constraints**：默认文法下 verdict 语义零变化（ADR-0255 §4.8 指称幻觉判定不变）；
  contracts 冻结 dataclass 不动；`verify_final_answer` 签名不变。
- **Dependencies**：唯一调用方是 `_judge_claim`（verifier.py 内部）；
  测试 `tests/infrastructure/source_verify/test_source_verify.py` 钉住流水线行为；
  生产侧 verify 尚无调用方（README 建议未落地），动它无回归风险。
- **Shape of the deepened module**：`SourceVerifier(policy, literal_extractor=...)`
  或模块级 `LiteralExtractor` Protocol；`_extract_literals` 成为默认实现并具名导出；
  `_LITERAL` 正则随默认实现走。
- **Test survival**：现有 source_verify 测试全绿；新增测试直接钉文法
  （中文日期形态、4 字符标识符边界等）而不必伪造 registry。
- **Deletion test verdict**：删掉 seam → 文法散回 verifier 私有 → concentrates。
  verdict：**通过**。

### RA-017
- **Constraints**：`known_session_event_types()` 返回集合不变（fail-closed 语义不动）；
  ADR-0268 §6 的 DSH 对齐不变，只是换个家。
- **Dependencies**：调用方 `lca/plugins/session/runtime/log/reader.py`；
  测试 `tests/observability/session/test_known_types_fail_closed.py` +
  `tests/session/test_session_public_api.py`。
- **Shape**：DSH surface 词表成为具名 frozenset 常量（放在 fold 词表旁或 DSH 对齐的
  reader 处，single source）；catalog.py 只 `types.update(...)` 它，删掉硬编码行。
- **Test survival**：fail-closed 测试继续全绿；新增断言 catalog 无手工字面量
  （或词表常量单测）。
- **Deletion test verdict**：删 catalog → 闭集散到各读路径 → concentrates
  （catalog 本体保留，只动词表来源）。verdict：**通过**。

### RA-018
- **Constraints**：`execute`/`validate` 对外行为零变化（validate 先拦，execute 的
  宽松分支实际不可达——收敛后保持该保证）。
- **Dependencies**：仅 tool_search.py 内部两处；`tool_search_factory` 注册路径不变。
- **Shape**：模块级 `_classify_args(args)` helper（返回三元组或小 dataclass）；
  两处共用同一口径（取 validate 的严格口径）。
- **Test survival**：`tests/infrastructure/tool_defer/test_tool_search*.py` 全绿；
  新增分类器单测（含 `namespaces=[]` 的口径）。
- **Deletion test verdict**：删 helper → 分类逻辑散回两处 → concentrates。
  verdict：**通过**。

## 丢弃（有证据）

1. 区 A Q1/Q2：5 模块分离是 README+docstring 文档化的刻意设计；policy.py 是
   earns-existence 的配置 switchboard。
2. 区 A Q4：`ensure_registry` 的 monkey-patch 是 legacy harness 刻意 fail-soft；
   verify 取具体类暂无收益（尚无生产调用方）。
3. 区 B 全区：5 文件精读——defer 编排是文档化的刻意设计；`_tool_to_spec` 复刻有
   "infrastructure must not import L2 nodes"注释背书；fail-soft/fail-fast 双轨有
   ADR-0256 B2 背书；8+ 测试文件钉住。
4. 区 C Q1：`derive_messages` 的函数级 import 是防循环的刻意延迟绑定；
   Q3 四遍树遍历是 2026-09-16 postmortem 后的刻意性能取舍；Q4 kernel 类型直引
   符合 Fact plane 分层。
5. Observation（不开 story）：`verify_final_answer` 尚无生产调用方——采集已接
   （`execute.py:271`），校验未接（README 建议 delivery_synth 未落地）。
   这是接线 gap，optimize 轮可顺手确认，非架构 deepening。

## Top recommendation

先做 **RA-016**：它是本轮唯一的"判定逻辑核心无接缝"问题——文法决定 verdict，
却是 verifier.py 的匿名私有物；且生产侧 verify 尚未被调用，现在是加缝的最低成本
窗口（零生产调用方 = 零回归风险）。RA-017 是 catalog 的手工单点消除，
RA-018 是同模块小收敛，可依次做。

Assessment complete: 3 stories written, top is RA-016.
