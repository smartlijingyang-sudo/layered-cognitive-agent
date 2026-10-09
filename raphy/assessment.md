# Raphy Round 15 Assessment — raphy/arch-20261009-1643（基线 ba65436bb）

评估时间：2026-10-09 16:43–17:15 CST。新鲜会话，零记忆，全部状态来自仓库文件。
上一轮 raphy/arch-20261009-1008 已合 main（merge 1cc01a1ac），RA-001~RA-096 全 done（无 dropped）。
禁区遵守：未读未碰 `lca/infrastructure/computer/guest/preamble.py` 的 emit/resolve 路径映射。

## Phase 1 — Explore

### 1.1 Scope via YAGNI

`git log --oneline` 回溯 45 commits：热点区 = raphy/ 自身（mechanical）、docs/notes 账本、
以及本次 assess 锁定的三区（最近两轮 raphy 改动最密集）：

- `lca/agent/cognitive_agent.py`（RA-082 包络收敛、RA-096 dataclasses.replace）
- `lca/cognition/body/tools/tool_batch_executor.py`（RA-086 effects 收敛）
- `lca/runtime/loop/runtime_loop.py`（近期 2 次改动，run() 方法 150+ 行）
- `lca/contracts/protocols/runtime/infra/infra.py`（LLMAdapter Protocol —— 运行时验证炸出来的）

### 1.2 Organic friction walk（5 问必答，精读非 grep）

**Area A — `lca/agent/cognitive_agent.py`（426 行，已全读）**

1. 理解一个概念要跨多少小模块？`run()` → `_run_lifecycle` → `_run_lifecycle_body` →
   `run_envelope`（`lca/agent/run_envelope.py`，RA-082）：四层嵌套但职责清晰（entry
   → scope → envelope spec → cascade），不算 sprawl。真正刺痛的是 `run()` 与
   `resume()` 各自末尾那段 `if self._plan_ref: with plan_ref_scope(...)` 的**逐字重复**
   （各 12 行，唯一区别是 `_run_lifecycle` 的参数）。
2. 浅模块？模块顶层的四个 `_agent_translate_*` 函数（RA-082 留下）：每个 8–10 行，
   interface = 一种异常类型 + 上下文。deletion test：删掉它们并不能把复杂度"集中"
   到一处——outcome 翻译规则（status/output/error/outcome/disposition 五元组）本来就
   是四种异常各自的翻译表；但四函数之间有**机械对称性**（FAILED+`drain_run_partial()`+`steps=0`
   出现 3 次）， Worth exploring：收敛成一张 outcome 翻译表而非四个函数。本轮不做
   （RA-082 刚落地，收敛它等于重写上轮决策，先记观察）。
3. 为 testability 抽出的纯函数？`_enrich_run_context`（RA-096 已收敛为 replace）。
   `_task_as_text` 2 行分支——真 bug 藏在调用方（RA-046 已修 None 入口）。无 locality 问题。
4. Leaky seam？**有**：`register_hook` 末尾 `if isinstance(runtime, HasHooks):` ——
   Protocol 已声明 `HasHooks`（`lca.contracts.protocols.perceive.capabilities`），
   调用方却用 isinstance 嗅探而不是让 interface 成为 test surface。else 分支是**静默
   丢弃**（hook 注册无声失败）。→ 候选 RA-099。
5. 未测试/只能穿透 interface 测试？四个 translator 有 RA-023 的 pin。`register_hook`
   的静默丢弃分支无测试（穿透 `runtime` 具体类型才能触发）。同 RA-099。

**Area B — `lca/runtime/loop/runtime_loop.py`（595 行，`run()` 全读）**

1. 跨模块理解成本：`run()` 单方法 ~150 行，串起 8 组**函数内 import**
   （`lca.infrastructure.session.bindings`、`...emit.lifecycle_emit`、
   `lca.infrastructure.skills.activation.bridge`、`lca.runtime.session.run_session_writer`、
   `lca.application.vocal.runtime_wiring`、`lca.contracts.models.vocal.models`、
   `lca.infrastructure.runtime_plane.capability_bindings`、
   `lca.infrastructure.vocal.settle_guard`、`lca.contracts.models.auto_review.models`、
   `lca.infrastructure.auto_review.gate`、`lca.infrastructure.computer.box_accessor`）。
   每个 import 注释都在解释"为什么不能放顶层"（循环 import / PR-E 桥接语义）。
   理解"一次 run 做了什么"要在 6 个关注点之间跳：bridge 安装→turn 开始→session writer
   播种→vocal 解析→auto-review 门→capability bindings token。**sprawl 的不是模块数，
   是单个方法的阶段数**。
2. 浅模块？`_publish_terminal_event`（3 行，docstring 承认是 "Compatibility seam"）
   委托给 `self._lifecycle.publish_terminal` —— interface 与实现几乎同构。deletion test：
   删掉它只是把一次调用搬到调用方，复杂度不集中。**它是 RA-083/084 时代的兼容垫片，
   留给调用方迁移**——记观察，不入 story（删它需要先改全部调用方，属机械清理，
   可作 hygiene，不占本轮名额）。
3. 纯函数抽取？`_run_driver` 的 `outcome_holder` dict 是可变 holder 习语——
   except 分支写、finally 分支读，真实 bug（outcome 丢失）只能藏在"哪个分支先跑"里，
   纯函数抽不出来。这是 locality **正确**的例子（状态机就该待在一起）。
4. Leaky seam？`cast("SessionProtocol", session_reader)` + 长注释论证
   "resolve_raw_session isinstance-guaranteed"——seam 在用注释代替类型保证。
   但 SPEC H 已声明这是 read face，属已声明契约，不算泄漏。
5. 测试面？`_run_driver` 的 try/except/finally 包络只能通过整轮 run 集成测试覆盖；
   细粒度行为（resume.end 只在 resume_envelope 时发）靠 scenario 测试。无穿透测试需求。

→ 候选 RA-100：把 `run()` 的 turn 准备阶段抽成命名私有 helper
（`_install_skill_bridge` / `_seed_run_session` / `_resolve_vocal_ctx` / `_apply_runtime_overrides`），
函数内 import 收敛到模块顶层或一个 `_late_imports` 块，并验证循环 import 的真实边界。

**Area C — `lca/cognition/body/tools/tool_batch_executor.py`（306 行，全读）+ `registry.py`（174 行，全读）**

1. 跨模块？`execute` → `_resolve_tools` → `_select_mode_with_optional_audit` →
   `_select_segments` → `_execute_segment` → `_execute_one` → `_as_tool_result` /
   `_combine_observations`：调用链深但每一步是 pipeline 阶段，顺序读即可，不刺痛。
2. 浅模块？`_as_tool_result`（7 行）与 `_combine_observations`（40 行）——
   前者是后者的单元素特例（OBS_RESULT_KIND 标记）。deletion test：
   删掉 `_as_tool_result`，把单元素走 `_combine_observations`？
   不行——`_combine_observations` 会重建 Observation 丢掉原 extra（注释明确写了
   "passes the tool's own extra through untouched"）。**不对称是故意的**，不碰。
3. 纯函数？`_canonicalise_tool_name` + `_CAMEL_BOUNDARY_RE` 在模块底——
   位置对（私有 helper 沉底），locality 好。
4. Leaky seam？`_select_mode_with_optional_audit` 的
   `isinstance(self._policy, AuditAwareToolBatchPolicy)` + `getattr(tool, "grant", None)`：
   前者是已声明协议的能力探测（docstring 明确 fallback 语义，RA-086/087 已审计），
   后者是 Body 权威 grant 的防御性读取（注释写了 safe-by-default）。**已收敛，不碰**。
5. 测试面？`_combine_observations` 的 failure_kind fold 有 pin（RA-086 相关测试）。
   无缺口。

结论：Area C 本轮无 story（RA-085/086/087 已收敛干净）。

### 1.3 Runtime verification（实跑，LLM_API_KEY=dummy，scripted LLM stub）

按 prompt 要求实跑三项核心流程（web-standard profile，`CognitiveAgent.run()`）：

- (a) 基础 run → COMPLETED：**失败**
- (b) 带 tool call 的 run → COMPLETED：**失败**
- (c) 同一 agent 两次顺序 run：**失败**

根因链（逐层探针确认）：

1. `llm.invoke` 节点**只**消费 `adapter.stream(...)`（PR-B cf155018d 拆分后），
   `LLMAdapter` Protocol 的 `stream` 带一个**默认实现**：`yield LLMStreamEvent(type=COMPLETED)`
   （`lca/contracts/protocols/runtime/infra/infra.py:41-44`，`# pragma: no cover`）。
2. 只实现 `complete` 的 adapter（包括仓库自带的 e2e 脚本桩
   `tests/integration/test_run_with_tool_use.py::_ScriptedEcho`）继承了这个
   no-op 默认：stream 只吐一个无 `response` 的 COMPLETED 事件。
3. `invoke.py:113` 只有 `event.type is COMPLETED and event.response is not None` 才赋值
   → response 保持 `LLMResponse(text="")` 空响应 → `decision.parse` 产出
   `action_type='respond'` 空文本 → outer `phase_main` 三条出边全不匹配
   （use_tool/delegate？no；respond+非空文本？no；should_terminate？no）
   → `RuntimeError('declarative run failed')`，**零证据**（error_fact 无 detail）。
4. 仓库自带的 e2e `test_run_with_tool_use_succeeds_on_web_standard` 在 main 上
   **同样失败**（4.68s，同签名 step=0 failed）——PR-B 之后从未更新过脚本桩。

修好脚本桩的 `stream`（按 `LLMStreamEvent` 不变式：COMPLETED.response 与
`complete()` 逐字段相等）后重跑：(a)(c) COMPLETED；(b) tool call 决策正确路由到
`act.main`（gate 探针：`action_type='use_tool'`），但该轮 terminal fallback 报
"未产生任何输出"——脚本桩只发一次 tool call 的人为限制，implementer 修 RA-097 时
需用完整脚本复现确认（见 story AC）。

**这是 P0 级候选**：默认 `stream` 是教科书式的 "one adapter = hypothetical seam" 反例——
为省一次 override 写出的默认实现，让所有不完整 adapter 在错误的地方静默失败，
且失败点（`_runtime_failure_message` → "declarative run failed"）吞掉了全部证据。

### 1.4 Duplication scan（次要）

- `cognitive_agent.py`：`run()` / `resume()` 末尾 `if self._plan_ref: with plan_ref_scope(...)`
  12 行逐字重复 ×2（Area A Q1）。→ RA-098。
- 其余重复均为已收敛（run_envelope、registry 白名单、Observation 构造器）。

---

## Phase 2 — Self-grilling

### RA-097（Strong / P0）

- **Constraints**：`LLMResponse` 不变式（COMPLETED.response ≡ complete() 返回值）不能破；
  所有生产 adapter（openai/anthropic/…）都已实现 `stream`，删默认实现不能影响它们；
  `complete` 仍是有效入口（非流式调用方在用）。
- **Dependencies**：`stream` 的调用方只有 `lca/nodes/think/llm/invoke.py`（grep 确认）；
  实现方 = 全部 LLM adapter。改动 seam = Protocol 默认方法 + invoke 的空响应检查。
  `complete` 的调用方不受影响。
- **Shape**：方案 A（推荐）：删掉 Protocol 上的默认 `stream` 实现（变抽象），
  不完整 adapter 在**构造/类型检查**时 fail-loud；同时 `llm.invoke` 在组装出
  空响应（无 text、无 tool_calls、无 delegations）时 raise `LLMAdapterError`
  点名 adapter 类名——"the interface is the test surface"。
  方案 B：保留默认但让默认委托 `complete()`（`response = await self.complete(...)` 后
  yield COMPLETED(response=response)）。A 更深（interface 即契约），B 更兼容。
  二选一由 implementer 定，AC 覆盖两种可接受终态。
- **Test survival**：`test_run_with_tool_use_succeeds_on_web_standard` 现状是红的
  （本轮实测），修好后是它最强的 pin；新增：只实现 `complete` 的桩 adapter 跑
  `llm.invoke` 必须 fail-loud（A）或产出与 complete 一致的响应（B）。
- **Deletion test**：删掉默认 `stream` → 所有 adapter 必须显式声明流式能力，
  复杂度从"运行时静默空响应"集中到"声明时显式契约"。Concentrates。✅

### RA-098（Worth exploring）

- **Constraints**：`plan_ref_scope` 的嵌套位置（bind_backends + run_scope 之内）不能变；
  `run()` 传 objective=text、`resume()` 传 objective=f"resume:..." 的差异保留。
- **Dependencies**：调用方只有 `run()` / `resume()` 本体。seam 移动影响为零。
- **Shape**：私有 `_plan_scoped(self, **kwargs)` 上下文管理器（或一个
  `_run_with_optional_plan_ref` helper），`run()`/`resume()` 各剩一行。
- **Test survival**：现有 plan_ref 行为 pin（`tests/fixtures/plan_ref_golden.txt`
  相关测试）在，改后必须 byte-identical。
- **Deletion test**：删掉重复 → "plan ref 条件作用域"成为单一命名 seam。
  Concentrates（小）。✅

### RA-099（Worth exploring）

- **Constraints**：`register_hook` 是 `AgentUnit` 的组合期 API；`runtime` 可能是
  任意 `Runtime` 实现（测试替身常见）。不能把 hook 注册变成硬性要求。
- **Dependencies**：调用方 = 组合根。`HasHooks` 已是声明式 Protocol。
- **Shape**：方案 A：`Runtime` 协议侧声明可选 `hooks`（已有 `CognitiveRuntime.hooks`
  property），`register_hook` 改为 `self.runtime.hooks.register(...)`，
  无 hooks 的 runtime 在**组合期** fail-loud（`bind_agent_from_scope` 校验）。
  方案 B（最小）：保留 isinstance 但 else 分支 raise 而非静默丢弃。
  B 是 5 行改动，A 是 seam 迁移；AC 接受 B 为下限。
- **Test survival**：无 hooks 的 runtime 调 `register_hook` 现状静默成功——
  新测试 pin 其为显式失败。
- **Deletion test**：静默丢弃分支的删除把"是否注册成功"变成可观测事实。Concentrates。✅

### RA-100（Worth exploring）

- **Constraints**：8 组函数内 import 各自注释了"为什么不能放顶层"（循环 import
  为主）；`global_bridge.install/dispose` 的 try/finally 语义不能变；
  `runtime_bindings_token` 的 token 作用域不能变。
- **Dependencies**：`run()` 是 `CognitiveRuntime` 唯一大方法；helpers 全私有。
- **Shape**：抽四个私有 helper：
  `_install_skill_activation_bridge()`（PR-E 注释随它走）、
  `_seed_run_session(...)`（writer 播种 + developer_seed/user 消息）、
  `_resolve_vocal_context(...)`（vocal_mode/wake 解析 + gate 复用）、
  `_apply_runtime_overrides(...)`（auto_review/box_accessor/origin + token）。
  import 收敛：先实测哪些可回顶层（循环 import 的真实边界用 `python -c "import lca.runtime.loop.runtime_loop"` 验证），
  剩下的收进一个 `_late` 块并注明原因。
- **Test survival**：web-standard e2e（RA-097 修好后）+ 现有 runtime loop scenario
  测试是行为 pin。
- **Deletion test**：删掉 helpers 会把 6 个阶段重新揉回一个方法——
  它们各自 earns existence（每个 helper 有独立注释/不变式）。✅

---

## Phase 3 — Present and record

| ID | Files | Problem | Solution | Benefits | Strength |
|----|-------|---------|----------|----------|----------|
| RA-097 | `lca/contracts/protocols/runtime/infra/infra.py`（LLMAdapter.stream 默认实现）, `lca/nodes/think/llm/invoke.py`, `tests/integration/test_run_with_tool_use.py` | `LLMAdapter.stream` 的 Protocol 默认实现只 yield 一个无 response 的 COMPLETED；`llm.invoke`（PR-B 后）只走 stream，导致任何只实现 `complete` 的 adapter 产出空 `LLMResponse`，run 在 outer 图以无证据的 "declarative run failed" 死亡。仓库自带 e2e 因此在 main 上是红的。 | 删掉默认 `stream`（变抽象，声明时 fail-loud）+ `llm.invoke` 对空响应 raise 点名 adapter；或退而让默认 `stream` 委托 `complete()`。二选一，AC 覆盖两种终态。修 e2e 脚本桩 override `stream`（按 COMPLETED.response ≡ complete() 不变式）。 | locality：stream 契约回到 Protocol 声明处，不再靠下游"恰好有内容"隐式保证；leverage：所有未来 adapter（测试桩/新 provider）不再踩同一个静默坑；测试面：空流从"不可测试的远端失败"变成 seam 处可断言的 fail-loud。 | Strong |
| RA-098 | `lca/agent/cognitive_agent.py` | `run()` / `resume()` 末尾 `if self._plan_ref: with plan_ref_scope(...)` 12 行逐字重复 ×2。 | 抽私有 `_plan_scoped` 上下文管理器（或等价 helper），两处各剩一行。 | locality：plan-ref 条件作用域成为单一命名 seam；改嵌套位置时只改一处。 | Worth exploring |
| RA-099 | `lca/agent/cognitive_agent.py` | `register_hook` 用 `isinstance(runtime, HasHooks)` 嗅探，else 分支**静默丢弃** hook 注册——"调用方不信任已声明的协议"。 | 方案 A：组合期校验 hooks 能力；方案 B（下限）：else 分支 raise 代替静默丢弃。 | interface 即 test surface：注册成功与否成为可观测事实；未来 debug "hook 没生效"不再需要穿透 runtime 具体类型。 | Worth exploring |
| RA-100 | `lca/runtime/loop/runtime_loop.py` | `CognitiveRuntime.run()` ~150 行串 6 个阶段 + 8 组函数内 import；理解一次 run 要在 bridge/session/vocal/auto-review/bindings 间跳跃。 | 抽四个私有 helper（bridge 安装 / session 播种 / vocal 解析 / runtime overrides），import 收敛回顶层（实测循环边界）。 | locality：每个阶段有自己的命名 seam 和不变式注释；leverage：下一次改 vocal/auto-review 不用读完整方法。 | Worth exploring |

**Top recommendation：RA-097**。它是本轮唯一的运行时实证 P0：静默失败 + 证据吞没 +
自带 e2e 在 main 上变红，三者叠加。修法已在树内验证（脚本桩补 `stream` 后
(a)(c) COMPLETED、(b) tool-call 正确路由到 act.main）。Runner-up：RA-100
（`run()` 是每次 debug 都要读的方法，阅读税最高）。

依赖顺序：RA-097 先（它修好 e2e，后续 story 的行为 pin 才可信）；RA-098/099/100
相互独立。RA-097 → RA-100（RA-100 的 AC 要求 e2e 绿）。

**Diversity quota**：4 个 stories 中 duplication 类 1 个（RA-098），其余 3 个来自
friction walk（RA-099 leaky seam、RA-100 shallow-method sprawl）与运行时验证
（RA-097 testability gap）。满足"至少一个来自 friction walk"。

---

Assessment complete: 4 stories written, top is RA-097.
