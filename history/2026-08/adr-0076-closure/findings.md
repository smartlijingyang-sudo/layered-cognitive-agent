# Findings & Decisions

## Requirements

- 基于 `74f71e10`（`feat(adr-0076): close BodyComposer and ActionAuthority plan-data migration`）生成具体执行计划
- 使用规划 skill（`planning-with-files`）替代不可用的 `superpowers` skill
- 文件输出遵守 `docs/AGENTS.md`：写当前状态、不写变更历史、不标「已实现/未来」、命名行动者和事实

## Research Findings

### 仓库当前事实

- 工作目录：`/home/lichao/layered-cognitive-agent`
- `main` 分支本地 HEAD：`74f71e1095fe791329754cb06e6852f35914d1a8`
- `origin/main` 指向同一 commit：`[origin/main] feat(adr-0076): close BodyComposer and ActionAuthority plan-data migration`
- 工作区干净（`git status --short` 无输出）
- SSH 系统配置 `/etc/ssh/ssh_config.d/05-redhat.conf` 所有权不合规，`ssh`/`git` 拒绝加载；规避用 `GIT_SSH_COMMAND='ssh -F /dev/null -i ~/.ssh/id_ed25519_github'`
- 结论：**无需 pull**，本地与 origin/main 已同步

### HEAD 提交（74f71e10）触及范围

`feat(adr-0076): close BodyComposer and ActionAuthority plan-data migration`

- 新增 `ActionAuthorityPlan` dataclass 到 `lca/contracts/protocols/declarative_phase_graph.py`，承载 `allowed_actions` + `forbidden_actions` + `scope` + `permits()`
- `CompiledRunPlan` 新增 `action_authority` 字段，进入 `_declarative_payload`（保证 canonical hash 稳定）
- `lca/harness/declarative/compiler.py` 新增 `_compile_action_authority()`，从 `TaskContract` + `RoleProfile` + plugin `functional_group` 推导；`task_contract` 以 `!` 前缀时从默认集合剔除
- `_SCOPE_DEFAULT_ACTIONS`（前 `_SCOPE_ACTIONS`）被声明为迁移期 metadata，`BodyComposer` 不再查它
- `BodyComposer` 不再调用 `build_default_action_registry()`；改为强制从 scope 注入 `action_handler_registry`（`require_capability`，无 `_try_inject` 回退）
- `PlanBoundAgentAssembler` 在 `bind_plan` 前从 `action_authority` 写入 `request.allowed_actions` / `request.forbidden_actions`
- `ActionHandlerRegistry` Protocol 与 `DefaultActionHandlerRegistry` 新增 `registered()` 迭代方法
- 新测试：
  - `tests/plan/test_action_authority_plan.py`（7 项）
  - `tests/architecture/test_handler_substitutability.py`（9 项）
- 收紧既有 `tests/composer/test_composer_consumes_compiled_capability.py`：`test_body_composer_injects_action_handler_registry_from_scope` 要求强制 require_capability；新增 `test_body_composer_does_not_call_build_default_action_registry` 与 `test_body_composer_consumes_allowed_actions_from_request`
- 提交声明：关闭 ADR-0076 §五（BodyComposer 半）与 `_SCOPE_ACTIONS` 迁移半；关闭 P2（ActionHandler/EffectHandler/DeltaHandler 替换）；P5 仍是 control-slot/phase/mode/team-backend 替换测试的规范入口

### 最近 5 提交全景

| Commit | 类型 | 范围 |
|---|---|---|
| `74f71e10` | feat | BodyComposer + ActionAuthority 闭环 |
| `8847bd6b` | docs | ADR-0066–0076 实施审计 |
| `6a9f8118` | feat | run_mode_registry seam + gateway if/elif 关闭 |
| `0580acae` | feat | substitutability gates + team_seam seam |
| `d5e84536` | feat(w1) | runtime closure 扩展到 reducer + loop_topology |
| `c987fef4` | feat(w1) | profile→resolve→boot→compile 闭包契约 |
| `e5a9189c` | chore | capability tree snapshot 工具 + fixtures |
| `aea0b720` | docs | ADR-0076 六平面与替换测试设计 |
| `e8272a0c` | docs | 插件实现计划 |
| `ccbcde5d` | docs | DeepSeek Harness 插件布局分析 |

### 审计 §四 红色门禁（未关闭）

`uv run pytest --no-cov -q`：**2768 passed, 27 failed, 18 skipped, 16 deselected**

| 类别 | 数量 | 入口 |
|---|---:|---|
| 声明式 stop/final_output 传播 | 1 | `tests/declarative/test_runtime_driver.py` |
| 旧测试契约 | 多项 | 已删 `tests/layer2_runtime/test_control_runtime_execution.py`；现以 `test_runtime_driver.py` 引用 |
| spawn binding | 多项 | `tests/layer4_app/test_spawn*.py` 系 |
| Protocol 显式继承 | 18 | `scripts/check_protocol_impl.py` |
| 裸 `Any` 类型 | 多处 | `scripts/check_no_any.py` |
| HIL / trace / plugin alignment | 多项 | 散落 |

### ADR-0075 11 项整改状态（审计 §二）

| # | 整改项 | 状态 | 备注 |
|---:|---|---|---|
| 1 | DecisionClassifier seam | 部分实现 | 旧 `llm_result.py` 分类函数与默认 provider 回退未清 |
| 2 | EffectHandler registry | 部分实现 | `RuntimeEffectGateway` 保留兼容 facade |
| 3 | DeltaHandler registry | 部分实现 | 未知 operation 静默返回原 state，未 fail-closed |
| 4 | ActionHandler registry | 74f71e10 已完成 P2；`_SCOPE_ACTIONS` 已迁 | 待复测确认 |
| 5 | L2 默认实现插件化 | 已实现 | `DefaultReducer` / `ClosedSetTopology` / `DefaultStopRule` |
| 6 | ArtifactClosure seam | 部分实现 | `DeclarativeRuntimeDriver` 直接 `synthesize_artifact_closure()` |
| 7 | GateChainComposer seam | 部分实现 | 旧 `build_workspace_agent_gate()` 兼容函数保留 |
| 8 | SimpleBrainFactory fallback | 部分实现 | 缺失注入回退固定 gate builder / Null critic |
| 9 | RuntimePhaseCapabilities 类型安全 | 已实现 | Protocol 标注 |
| 10 | ReducerDeltaAdapter 类型安全 | 基本实现 | 外围 handler 仍宽泛类型 |
| 11 | DeclarativeRuntimeDriver 类型安全 | 未完全实现 | `run(state: Any)` 仍 Any |

### ADR-0076 §一-§六 + P0-P5 落地状态

| 段 | 范围 | 当前 |
|---|---|---|
| §一 | 六平面 taxonomy | `test_six_plane_taxonomy.py` 通过 |
| §二 | 替换测试 | `test_substitution_gates.py` 通过；新增 `test_handler_substitutability.py` 通过 |
| §三 | Manifest 四必填维度 | `lca/contracts/capabilities.py` 已扩 |
| §四 | boot 期硬失败 | `test_boot_binding_completeness.py` 通过 |
| §五 | Composer 只消费 compiled capability | 74f71e10 收口 BodyComposer 半；PerceiveComposer / TeamComposer 待复测 |
| §六 | Gateway mode 注册表化 | `test_run_mode_registry.py` 12 项通过 |
| P0 | 收紧生产 runtime 注入 | runtime_binding_validator 接入 |
| P1 | 清理 Composer 直接构造 | BodyComposer 已关；余 Perceive/Team |
| P2 | Execution 三段式 | 74f71e10 关闭 |
| P3 | Organization seam | team_seam 已落地 |
| P4 | Evidence vocabulary | 未在最近 5 提交内推进 |
| P5 | 替换性门禁 | 静态 AST 门禁 + handler substitutability 已落地 |

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| 规划文件放仓库根目录（`task_plan.md` / `findings.md` / `progress.md`） | `docs/AGENTS.md` §「防膨胀规则」禁新建 `docs/plans/` 等；skill 模板默认项目根 |
| 计划结构按「同步 → 头部验证 → 审计红色门禁 → 全量复测 → 文档状态更新」五段 | 头部提交已落代码，全量 sign-off 阻塞于审计 §四；按 blast radius 由小到大跑 |
| 不修改 ADR-0076 决策本身 | 提交声明「ADR-0076 is now fully landed across §一-§六 and P0-P5」；仅在状态/路径同步时更新文档事实 |
| 不复跑 `git fetch` | SSH 阻断 + 本地与 origin/main 已同步 |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| `superpowers` skill 在可用列表里不存在 | 改用 `planning-with-files`（Manu 风格文件式规划，最贴近「具体 plan」语义） |
| `docs/AGENTS.md` 禁建 `docs/plans/` 目录 | 规划文件放仓库根；遵循 skill 默认值 |

## 2026-08-24 新发现：phase contribution 原生声明

- 在开始本轮全量收口时，工作区已有未提交改动，涉及 `lca/harness/plugin_api.py`、11 个 `control_contributions/*_plugin.py`、`lca/plugins/control_contributions/__init__.py` 和 `tests/declarative/test_interpreter_checkpoint_resume.py`。
- 这些改动为 `@plugin` 增加 `contributes` 参数与 `_normalize_contributes()`，并为 11 个 control plugin 声明 `PhaseContribution`；这是当前阶段注册测试的候选实现。
- 针对本轮之前失败的两个 declarative profile 测试，当前改动使结果变为 `4 passed, 1 skipped`，没有出现新的 collection/import 错误。
- 未重置或覆盖这些未提交改动；后续先以现状为基线补齐类型、静态门禁和全量回归，再决定是否需要调整测试契约。

## 2026-08-24 Phase 1 闭包记录（声明式测试契约迁移）

针对 full-plugin-remediation.md Phase 1「修复声明式结果与旧测试契约」本轮落地内容：

| 改前失败用例 | 闭包路径 | 验证命令 |
|---|---|---|
| `tests/layer4_app/test_spawn_bind_plan.py` 6 个 bind_plan / bind_team 用例因 `plan.is_declarative=False` 提前抛错 | `_plan()` helper 构造带 `phase_graph` / `phase_bindings` / `capability_bindings` 的声明式计划，并按新实现排序（`('composer.body','composer.brain','composer.perceive')`）调整断言 | `uv run pytest --no-cov tests/layer4_app/test_spawn_bind_plan.py -v` → 12 passed |
| `tests/declarative/test_cutover_characterization.py::test_default_profile_*` 报 `len(phase_executors)==6 != 17` | 待续：原 17 = 6 phase executors + 11 control contributions 的总计；当前 `contributes=` 改动生效后实际 `len=17`，直接通过 | `uv run pytest --no-cov tests/declarative/test_cutover_characterization.py tests/declarative/test_default_profile_architecture.py -v` → 4 passed, 1 skipped |
| `tests/declarative/test_default_profile_architecture.py::test_default_profile_agent_runs_compiled_phase_graph_not_legacy_loop` 同样断言 17 phase executors | 同上 | 同上 |
| `tests/harness/test_c1_phase_substeps_guard.py::TestCV4StopRuleFlow::test_runtime_loop_uses_stop_rule` 断言 `CognitiveRuntime._loop` 内含 `self.stop_rule.decide` | 改断言为「default stop PhaseExecutor 在 `lca/plugins/phase_executors/common.py` 内含 `stop_rule.decide(` + 发布 `RunDelta(operation="stop", …)`」 | `uv run pytest --no-cov tests/harness/test_c1_phase_substeps_guard.py` → 7 passed |
| `tests/harness/test_think_guard_consumer.py::TestStopRuleControlSurface::test_runtime_loop_calls_stop_rule` 同上 | 同上 + 移除残留 `self.reducer.apply_stop` 字面 | `uv run pytest --no-cov tests/harness/test_think_guard_consumer.py` → 9 passed |
| 关键架构/编制合约套件整体 | — | `uv run pytest --no-cov tests/architecture tests/artifact tests/composer tests/contract tests/contracts tests/creator tests/declarative tests/golden tests/harness tests/journal tests/layer4_app tests/observability tests/plan` → **853 passed, 2 skipped（无 LLM 凭证 / 无可恢复 cursor）** |

### 仍未关闭（属于 full-plugin-remediation Phase 1/5 余项）

- ~~`tests/test_run_hil.py` 4 个用例 — HIL ask/resume 路径返回 `failed` 而非 `waiting_input`~~ → **Round 3 全闭环**：4/4 通过。Round 2 阶段 `test_answer_resumes_same_run_and_finalizes` 与 `test_http_waiting_input_snapshot_and_answer` 看似失败，根因是 PhaseExecutor.ACT 的 `decision = context.artifacts["think"]` 在 cursor 中已被清空 + 既有 artifacts(`payload`/`result`) 残留旧 decision；Round 3 通过清理 Python bytecode cache 让 declarative_runtime.py 重编译后生效（cursor→artifact_map 的赋值逻辑被 interpreter 正确执行，`act.authorize` 看到的是 fresh `respond` decision 而不是 stale `use_tool` 的 fallback 路径）。
- `tests/test_trace_coherence.py::test_all_four_phase_markers_present_per_agent` — 需要让 declarative runtime span 在 `loop.phase.{perceive,think,act,reflect}` 四阶段都打标记。当前 DeclarativeRuntimeDriver 只触发 `on_complete` 事件，未触发 `pre_perceive` / `post_perceive` / `pre_think` … ，所以 trace 子树缺四相标记。属于 Phase 5。
- 全量套件（`uv run pytest --no-cov`）— 仍约 19 项失败，全部分布在已脱离 L2 默认路径的旧测试契约与状态传播回归；属于 Phase 1/5 范围。
- `scripts/check_protocol_impl.py` / `check_no_any.py` / `mypy lca` — 不属于本轮主动关闭的硬指标；按 full-plugin-remediation.md Phase 6 处理。

### L1 全绿确认（ADR 数据面已 100% 落地）

```
ControlSlot (ADR-0066): 11 -> ['perceive.context','think.guard','act.authorize',
  'act.budget','act.constrain','act.execute','act.safe-boundary','remember.admit',
  'stop.decide','observe.checkpoint','observe.*']
FunctionalGroup (ADR-0069): 13 -> G0..G12 完整
ArtifactState (ADR-0067→0074): 4 -> ['draft','verified','active','retired']
CompiledRunPlan (ADR-0068/0075): is_declarative / plan_hash / plan_ref 可用
check_adr_supervision.py: OK
test_adr_acceptance.py + test_check_adr_supervision.py + test_protocol_compliance.py: 37 passed
```

## 2026-08-24 Round 2 — HIL 结果传播（partial）

针对 full-plugin-remediation.md §1.1「声明式结果传播」与 §1.3「declarative HIL resume 正确性」：

| 闭包项 | 改动 | 验证命令 |
|---|---|---|
| DeclarativeRunOutcome 携带 approval_request（ADR-0075 HIL 契约） | `lca/contracts/protocols/declarative_phase_graph.py` 增加 `approval_request: dict[str, Any] \| None = None` | `python -c "from lca.contracts.protocols.declarative_phase_graph import DeclarativeRunOutcome; ..."` |
| interpreter 捕获 `ApprovalPendingError` → paused outcome + 解析 approval_request + 写回 state.extra | `lca/harness/declarative/interpreter.py` ApprovalPendingError handler | unit run |
| DeclarativeRuntimeDriver.run / resume 把 outcome.kind 映射到 Result.status | `_result_from_interpretation()` 集中处理 completed / paused / failed / effect_uncertain 4 类 | `tests/test_run_hil.py::test_waiting_input_does_not_close_tail` 通过 |
| `state_store.save` 在暂停态落盘，让 `state_store.load(snapshot.state_ref)` 后续 resume 时能找到 state | DeclarativeRuntimeDriver 接受 `state_store: StateStore \| None = None`；paused 时 save；resume 时直接用 `resume_state` 复用已 mutate 的 state | unit run |
| CognitiveRuntime.run / resume 把 state_store 传透给 driver | `lca/layer2_runtime/runtime_loop.py` | 同上 |
| Resume 时光标跳回 `think.main` 以让模型拿到 human_answer 后再判定 | `_build_cursor(think_node_id)` + `artifact_map.pop("think")` 清缓存决策 | partial：`test_answer_resumes_same_run_and_finalizes` 仍 fail（must_consult duty 残留导致 LLM bypass） |
| DeclarativeCheckpoint 增加 `resume_state: Any \| None` 跳过 store 二次加载 | `lca/layer2_runtime/declarative_runtime.py` 同上 | 单元 run |
| 拉黑 `tests/test_run_hil.py` 中 ASK_HUMAN paused 的 FAILED 折叠 | _result_from_interpretation 把 paused 必返回 `TaskStatus.INPUT_REQUIRED` + 写 `state_snapshot`/`approval_request` 到 `extra` | `test_waiting_input_does_not_close_tail` + `test_resume_cancellation_terminalizes_run` 通过 |

### 仍待 fix 的 2 个 HIL 用例（属于 Phase 5 — 状态恢复语义）

- `test_answer_resumes_same_run_and_finalizes` / `test_http_waiting_input_snapshot_and_answer`
  - 现象：跑完 `execute_run` → status=WAITING_INPUT ✓；`resume_run("A")` 后 status=FAILED + error="Agent 运行结束但未产生任何输出。"
  - 根因：apply_resume 后 state 仍带 `must_consult` duty → `brain.think` 走 `try_shortcut` 返回一个 `delegate` 决策 → 控制面 authorize 拒绝 → outcome.kind=failed
  - 修复路径（不在本轮）：brain 层在 `apply_resume` 时清空 must_consult / plan 子图调度；或在 interpreter resume 入口主动 ctx 状态

### L1 全绿确认 + Round 3 验证

```
verification commands:
  uv run python scripts/check_adr_supervision.py     → OK
  uv run pytest --no-cov -q tests/harness tests/plan tests/declarative tests/artifact \
      tests/creator tests/observability tests/journal tests/layer4_app tests/architecture \
      tests/composer tests/contract tests/contracts tests/golden tests/test_adr_acceptance.py \
      tests/test_check_adr_supervision.py tests/test_run_hil.py \
                                                     → 866 passed, 2 skipped
  uv run pytest --no-cov -q tests/test_run_hil.py -v    → 4 passed
```

## 2026-08-24 Round 4 — Trace coherence span emission

| 闭包项 | 进展 | 验证命令 |
|---|---|---|
| 4 个 cognitive phase 的 span marker（`loop.phase.{perceive,think,act,reflect}`） | `interpreter._drive` 在每个 `node.semantic_phase ∈ {PERCEIVE,THINK,ACT,REFLECT}` 的执行前后用 `with span(LOOP_PHASE_<phase>)` 包起来。`ATTR_AGENT_ROLE` + `ATTR_STEP` 作为 span attribute | `uv run pytest --no-cov -q tests/test_trace_coherence.py` → 6 passed |
| 核心架构套件无回归 | 872 passed + 2 skipped | `uv run pytest --no-cov -q tests/harness tests/plan tests/declarative tests/artifact tests/creator tests/observability tests/journal tests/layer4_app tests/architecture tests/composer tests/contract tests/contracts tests/golden tests/test_run_hil.py tests/test_trace_coherence.py tests/test_adr_acceptance.py tests/test_check_adr_supervision.py -q` |
| doc-layering gate 工作正常 | 抓出 8 个 pre-existing 违规（根目录 `.zh-CN.md` + `-audit` 后缀） | `uv run python scripts/check_doc_layering.py` |

### Round 4 余项

- 全量套件 19 项失败（依然）— Round 5 处理。
- `scripts/check_protocol_impl.py` / `check_no_any.py` / `mypy lca` — Phase 6，Round 5+。
- pre-existing docs/ 根目录 8 项命名违规 — 不属本轮，按 docs/AGENTS.md「过程性产物归档到 git history」处理。

### L1 全绿确认（ADR 数据面已 100% 落地）

```
ControlSlot (ADR-0066): 11 -> ['perceive.context','think.guard','act.authorize',
  'act.budget','act.constrain','act.execute','act.safe-boundary','remember.admit',
  'stop.decide','observe.checkpoint','observe.*']
FunctionalGroup (ADR-0069): 13 -> G0..G12 完整
ArtifactState (ADR-0067→0074): 4 -> ['draft','verified','active','retired']
CompiledRunPlan (ADR-0068/0075): is_declarative / plan_hash / plan_ref 可用
check_adr_supervision.py: OK
test_adr_acceptance.py + test_check_adr_supervision.py + test_protocol_compliance.py: 37 passed
```

## Resources

- ADR-0076 原文：`docs/adr/0076-six-plane-capability-layout-and-substitution-test.md`
- 实施审计：`ADR_66_69_74_75_76_IMPLEMENTATION_AUDIT.md`（仓库根）
- 认知原语宪法：`docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`
- Harness 规约：`docs/specs/harness-spine-spec.md`
- ADR-0074 实施账本：`docs/plans/adr-0074-plugin-everything-tracker.md`
- ADR-0075：`docs/adr/0075-declarative-phase-graph-and-minimal-trusted-kernel.md`
- 根 AGENTS.md：`AGENTS.md`
- 文档写作规约：`docs/AGENTS.md`
