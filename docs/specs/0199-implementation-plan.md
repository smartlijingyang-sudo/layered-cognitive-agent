# ADR-0199 完整 PR 实施计划

> **状态：** Living — Phase 0 Done；Phase 1 Approved（In Progress）
> **权威：** [ADR-0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) · [ADR-0200](../adr/0200-hermes-product-capabilities-absorption.md)（产品能力，**不在本计划**）
> **用法：** 每个 PR 必须引用 `PR-0199-Px-yy`；合并前跑 §2 验证矩阵；Coding Agent 开工前读 §1 + 对应 PR 的 **Agent Brief**。

---

## 0. 总览

| Phase | 主题 | PR 数 | 日历（估，并行） | 硬依赖 |
|---|---|---|---|---|
| **P0** | ADR 冻结 | 2 | Done | — |
| **P1** | Runtime Facade + RunIntent | **14** | 2–3 周 | P0；ADR-0194 事实单轨 P1 达标 |
| **P2** | Plugin Doctor | **12** | 2–3 周 | P1-07（resolve_activation 存在） |
| **P3** | Privilege / PluginOrigin | **10** | 3–4 周 | P2-08（DoctorReport 稳定） |
| **P4** | ResourceRegistry + PlanProposal | **8** | 3 周 | P3-06 |
| **P5** | External plugin trust tier | **6** | 2 周 | P3-04 |
| **合计** | | **52 PR** | ~10–12 周（3 Lane 并行） | |

**MVP 闭包（可先 ship）：** P0 + P1 全轨 + P2-01…P2-08 + P2-12 = **24 PR** → 统一入口 + profile doctor CI。

### 0.1 并行 Lane

```text
Lane R  Runtime     P1（contracts → facade → wire adapters → acceptance）
Lane D  Doctor      P2（schema → compile dry-run → CLI → web render）
Lane G  Governance  P3 → P4 → P5（privilege → resource → external trust）

可并行（无 import 冲突时）:
  Week 1:   P1-01 ‖ P1-02 ‖ P1-04（纯 contracts）
  Week 2:   P1-07 ‖ P1-08；P2-01 ‖ P2-02（Doctor 纯类型）
  Week 3+:  P1-09…P1-14 串行于 facade；P2-03…P2-06 可与 P1-10 并行
  P3 起:    Lane G 等 P2-08
```

### 0.2 分支与 PR 标题

```text
PR-ID:     PR-0199-P1-03
branch:    adr0199/p1-03-activation-ref-hash
title:     feat(contracts): SessionActivation and activation_ref hashing
```

### 0.3 与 ADR-0200 边界

| 本计划（0199） | [0200 产品计划](0200-implementation-plan.md)（待建） |
|---|---|
| RunIntent / RuntimeFacade / Doctor / PluginOrigin / ResourceRegistry | review-fork / Curator / ContextEngine / MemoryProvider / no_agent |
| **可立即启动 P1** | **须等 0187 P0→P2** |

**禁止：** 在 0199 PR 内实现 Curator、review-fork、ContextEngine 产品逻辑。

---

## 1. Coding Agent 执行契约（每个 PR 强制）

### 1.1 开工前必读（按序，不得跳过）

| 顺序 | 文档 / 代码 | 目的 |
|---|---|---|
| 1 | [AGENTS.md](../../AGENTS.md) §1 七问 + §3 不变量 | 契约边界 |
| 2 | [ADR-0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) 对应 Phase + I-HPC-* | 本 PR 不变量 |
| 3 | 本文 PR 行的 **Read First** | 实现锚点 |
| 4 | [runtime-entry-walkthrough.md](runtime-entry-walkthrough.md) | 现有 L0–L7 链（P1 PR 必读） |
| 5 | [plan-compile-and-execute-walkthrough.md](plan-compile-and-execute-walkthrough.md) | K1/K2（P1/P2 PR 必读） |

### 1.2 禁止事项（违反即 Reject PR）

1. **临时代码：** 禁止 `TODO` 无 owner/delete-when；禁止 `# FIXME` 替代正确设计；禁止 `if True` 占位分支进 main。
2. **绕边界：** L0 不得 `resolve_profile` / `compile_plan`（P1-09 前旧路径须 COMPAT 标注）；L0 不得 `Session.append`。
3. **平行 SSOT：** 禁止第二套 plan 缓存、禁止 handler 内拼 `CompiledRunPlan`。
4. **Service Locator：** 禁止新 global mutable registry（I-HPC-9）。
5. **Doctor 副作用：** Doctor 路径禁止网络、写盘、K3 fiber setup（I-HPC-7）。
6. **弱化测试：** 禁止只测 mock 不测行为；禁止删除既有绿测试换「能跑」。

### 1.3 每个 PR 最小交付单元（Definition of Done）

```markdown
- [ ] 仅改 PR 范围文件（+ 测试 + 必要 re-export）
- [ ] 新增/变更 public 签名先有 contracts Protocol 或 dataclass
- [ ] 至少 1 个**行为**回归测试（非仅 snapshot）
- [ ] `uv run ruff check` + `uv run ruff format --check` 通过
- [ ] 本文 §2 中该 PR 列出的 pytest 全绿（exit 0）
- [ ] 无新增 lint-imports **本次**违规（区分 AGENTS §6 基线失败）
- [ ] COMPAT 块写满 owner/from/to/delete_when/forbidden_new_usage
- [ ] PR 正文含 ADR-0199 条目 + delete-when 命令
```

### 1.4 Agent Brief 模板（复制到 PR / Task 描述）

```text
Task: PR-0199-Px-yy — <title>
Authority: ADR-0199 Phase X; I-HPC-n,…
Read First: <paths from table below>
Implement: <single responsibility — one module or one adapter>
Do NOT: temp shims without COMPAT; bypass RuntimeFacade after P1-10; import cognition from transport
Verify: <exact bash from PR row>
If blocked: stop and report missing seam — do not invent parallel mechanism
```

---

## 2. 全局验证矩阵

| 阶段 | 命令 | 通过标准 |
|---|---|---|
| 每 PR | `uv run ruff check && uv run ruff format --check` | exit 0 |
| 每 PR | `uv run pytest <PR-tests> -q` | exit 0；区分 xfail baseline |
| P1 轨 | `uv run pytest tests/architecture/test_0199_phase1_acceptance.py -q` | exit 0（P1-12 后存在） |
| P1 轨 | `uv run pytest tests/golden/test_8_profiles.py -q` | exit 0（无 profile 回归） |
| P2 轨 | `./scripts/lca-ops doctor profile profiles/web-standard.yaml --ci --json` | exit 0（P2-08 后） |
| P2 轨 | `uv run pytest tests/harness/diagnostics/test_plugin_doctor.py -q` | exit 0 |
| P3 轨 | `./scripts/lca-ops audit-plugin-shape` | 无**新增** error |
| 门禁 | `uv run pytest tests/scenario/refactor/test_refactor_guards.py -q -k 0199` | exit 0（逐 PR 添加） |
| 文档 | `uv run python scripts/verify_md_links.py`（仅改 docs 时） | 无**新增**断链 |

**基线协议：** `lint-imports` / `check_package_contracts.py` 既有失败须在 PR 正文标注「pre-existing」；不得声称全绿。

---

## 3. P0 — ADR 冻结（Done）

| PR-ID | 状态 | 交付 |
|---|---|---|
| P0-01 | Done | ADR-0199 正文 + README 索引 |
| P0-02 | Done | documentation-map 入口 + 本计划占位 |

---

## 4. P1 — Runtime Facade + RunIntent（14 PR）

> **目标：** 同一 `RunIntent` + 同一 profile → 相同 `plan_ref`；L0 不 direct resolve/compile（COMPAT 除外）。

### P1 关键路径

```text
P1-01 → P1-02 → P1-03 → P1-05 → P1-07 → P1-10 → P1-11 → P1-12
         ↘ P1-04（Protocol，可与 P1-03 并行）
P1-08（adapter 纯函数）→ P1-09（transport）→ P1-10
P1-06（hash 纯函数）在 P1-03 前或并行
```

| PR-ID | 标题 | Read First（必读源码） | 交付（精确路径） | 实现要点（≤5 步） | 测试（先写后实现） | 验证命令 | 依赖 | 并行 |
|---|---|---|---|---|---|---|---|---|
| **P1-01** | feat(contracts): RunIntent frozen dataclass | `terminal/port.py` RunRequest；`conversation.py` ConversationTurn | `lca/contracts/runtime/intent.py`：`RunIntent` | 1) 仅数据字段，无 ctx 2) `frozen=True, slots=True` 3) `__post_init__` 校验非空 profile/user_text 4) `to_jsonable()` 若项目惯例需要 5) `__all__` 导出 | `tests/contracts/runtime/test_run_intent.py`：构造、reject 空 profile、equality | `pytest tests/contracts/runtime/test_run_intent.py -q` | P0 | P1-02 |
| **P1-02** | feat(contracts): TrustEnvelope + PluginOrigin | ADR-0199 §3.2；`plugin_contract.py` CapabilityContract | `lca/contracts/runtime/trust.py` | 1) `PluginOrigin` Literal source/trust 2) `TrustEnvelope` tuple origins + granted privileges 3) 默认 trust=untrusted for project/pip 4) 纯类型无 I/O | `tests/contracts/runtime/test_trust_envelope.py` | 同上目录 | P0 | P1-01 |
| **P1-03** | feat(contracts): SessionActivation | ADR-0199 §2.2.2；`plan.py` CompiledRunPlan | `lca/contracts/runtime/activation.py` | 1) 字段：activation_ref, plan_ref, graph_ref, plugin_set_ref, profile_path, session_id, trust_envelope 2) **不** embed mutable ctx 3) 可选持有 `CompiledRunPlan` 只读引用 4) 构造时 validate refs 非空 | `tests/contracts/runtime/test_session_activation.py` | `pytest tests/contracts/runtime/test_session_activation.py -q` | P1-01 | — |
| **P1-04** | feat(contracts): RuntimeFacade Protocol | ADR-0199 §2.2.3；`contracts/protocols/` 既有 Protocol 风格 | `lca/contracts/runtime/facade.py` | 1) `resolve_activation(intent) -> SessionActivation` 2) `dispatch_run(activation) -> RunHandle`（RunHandle 可先 type alias str run_id） 3) `dispatch_resume(...)` 可先 `...` 或 NotImplemented 4) `@runtime_checkable` 若惯例需要 | `tests/contracts/runtime/test_runtime_facade_protocol.py`：structural subtyping | `pytest tests/contracts/runtime/test_runtime_facade_protocol.py -q` | P1-03 | P1-03 |
| **P1-05** | feat(contracts): runtime package exports | — | `lca/contracts/runtime/__init__.py` | 1) 重导出 intent/trust/activation/facade 2) 不引入 harness/kernel import | import 测试 | `pytest tests/contracts/test_declarative_contract_modules.py -q -k runtime` | P1-04 | — |
| **P1-06** | feat(harness): activation_ref pure hash | `lca_kernel/plan/plan.py` plan_ref 算法；`plan_compiler.py` | `lca/harness/runtime/activation_ref.py` | 1) 纯函数 `compute_activation_ref(plan_ref, graph_ref, plugin_set_ref, session_id)` 2) 稳定 canonical JSON + sha256 3) **确定性**（C8）4) 无 env 读取 | `tests/harness/runtime/test_activation_ref.py`：同输入同 hash；顺序无关 | `pytest tests/harness/runtime/test_activation_ref.py -q` | P1-03 | P1-04 |
| **P1-07** | feat(application): PlanResolutionService | `harness/profile/resolve/resolve.py`；`composition/plan_compiler.py`；`kernel/kernel.py` _inspect | `lca/application/runtime/plan_resolution.py` | 1) 类只做 resolve+compile→refs 2) 方法 `resolve_refs(profile_path, *, compile_options=None)` 3) 返回 `(plan_ref, graph_ref, plugin_set_ref, CompiledRunPlan)` 4) 不 boot fiber 5) 复用现有 `resolve_profile` + `compile_plan` | `tests/application/runtime/test_plan_resolution.py` vs golden profile | `pytest tests/application/runtime/test_plan_resolution.py -q` | P1-06 | — |
| **P1-08** | feat(application): RunIntent wire adapters | `command_endpoints.py` `_to_run_request`；`infrastructure/cli/commands/runs/` | `lca/application/runtime/adapters/intent_from_transport.py`；`intent_from_cli.py` | 1) `run_request_to_intent(RunRequest) -> RunIntent` 2) CLI args → RunIntent 3) **不** import starlette 4) surface 字段：`http`/`cli`/`test` | `tests/application/runtime/test_intent_adapters.py` | `pytest tests/application/runtime/test_intent_adapters.py -q` | P1-01 | P1-07 |
| **P1-09** | feat(application): DefaultRuntimeFacade resolve | P1-07 PlanResolutionService；`session/` session_id 生成惯例 | `lca/application/runtime/default_facade.py` | 1) 实现 `RuntimeFacade` 2) `resolve_activation`：intent→session_id→refs→SessionActivation 3) inject PlanResolutionService（构造注入，非 global）4) 暂不 dispatch | `tests/application/runtime/test_default_facade_resolve.py` | `pytest tests/application/runtime/test_default_facade_resolve.py -q` | P1-07,P1-08 | — |
| **P1-10** | feat(application): DefaultRuntimeFacade dispatch | `carrier/runs/lifecycle/lifecycle.py` RunLifecycleCoordinator；`execute/` | `default_facade.py` 扩展 dispatch | 1) dispatch 委托现有 Coordinator/Driver **不复制** loop 2) activation 只读传递 plan_ref 3) 禁止 transport import 4) RunHandle=现有 run_id 类型 | `tests/application/runtime/test_default_facade_dispatch.py` | `pytest tests/application/runtime/test_default_facade_dispatch.py -q` | P1-09 | — |
| **P1-11** | refactor(transport): HTTP create_run → RunIntent path | `command_endpoints.py` create_run；P1-08 adapter | `command_endpoints.py` 改 orchestration | 1) decode → RunIntent via adapter 2) facade.resolve + dispatch 3) RunPort 暂保留 COMPAT 双路径开关 `LCA_RUNTIME_FACADE=1` 4) 默认走 facade | `tests/lca_plugins/transport/webserver/test_runs_sessions.py` 全绿 | `pytest tests/lca_plugins/transport/webserver/test_runs_sessions.py -q` | P1-10 | — |
| **P1-12** | test(arch): plan_ref cross-surface parity | golden profiles | `tests/architecture/test_0199_phase1_acceptance.py` | 1) 同一 RunIntent：facade resolve vs 直接 compile_plan plan_ref 一致 2) CLI adapter vs HTTP adapter intent 一致 3) HPC-L2 grep 骨架 | 本文件即测试 | `pytest tests/architecture/test_0199_phase1_acceptance.py -q` | P1-11 | — |
| **P1-13** | refactor(cli): lca-ops runs create via facade | `infrastructure/cli/commands/runs/runs.py` | CLI 改经 facade | 1) 移除 CLI 内联 resolve_profile（COMPAT 注释）2) 与 HTTP 同 Path | CLI integration test | `pytest tests/scenario/runs/ -q -k create` | P1-11 | P1-12 |
| **P1-14** | chore(arch): HPC-L2 grep gate + COMPAT inventory | ADR-0199 §12 | `tests/architecture/test_0199_compat_gates.py`；`scripts/route_legacy_patterns.py` 扩展 | 1) grep handler 直 resolve 2) 允许 COMPAT 标记豁免列表 3) forbidden_new_usage 文档化 | grep test | `pytest tests/architecture/test_0199_compat_gates.py -q` | P1-12 | — |

**P1 出口：** `RunIntent` contracts 稳定；`DefaultRuntimeFacade` 为 HTTP/CLI 主路径；`test_0199_phase1_acceptance` 绿；无新 direct resolve in transport（除 COMPAT）。

---

## 5. P2 — Plugin Doctor（12 PR）

> **目标：** Doctor = compile dry-run + 只读报告；**不**复制 Hermes 平行 scanner。

| PR-ID | 标题 | Read First | 交付 | 测试 | 验证 | 依赖 | 并行 |
|---|---|---|---|---|---|---|---|
| **P2-01** | feat(contracts): DoctorFinding + severity | Hermes `doctor_report.py`（只读参考）；ADR-0199 §5.2 | `lca/contracts/diagnostics/doctor.py` | frozen dataclass；code regex `DOC-[A-Z]+-\d+` | unit | P1-05 | P2-02 |
| **P2-02** | feat(contracts): DoctorReport aggregate | — | 同文件：`DoctorReport` summary/findings/to_json | roundtrip JSON | unit | P2-01 | — |
| **P2-03** | feat(harness): ProfileCompileDryRun | `plan_compiler.py`；`resolve.py`；`declarative/controls/validation.py` | `lca/harness/diagnostics/doctor/compile_dry_run.py` | 1) 无 K3 2) 捕获 PlanCompilerError → Finding 3) 不写 journal | `tests/harness/diagnostics/test_compile_dry_run.py` | P1-07 | P2-04 |
| **P2-04** | feat(harness): PluginShapeDoctor pass | `scripts/check_plugin_shape.py` | `doctor/plugin_shape.py` 复用脚本逻辑为 lib | 与脚本 parity | P2-03 | P2-05 |
| **P2-05** | feat(harness): CapabilityCardinalityDoctor | `capability_plan_resolver.py` | `doctor/capability_cardinality.py` | duplicate owner → DOC-CAP-001 | unit | P2-03 | P2-04 |
| **P2-06** | feat(harness): PhaseGraphDoctor | `phase_graph_compiler.py`；`tests/declarative/test_phase_graph.py` | `doctor/phase_graph.py` | PG-* errors → findings | unit | P2-03 | P2-04 |
| **P2-07** | feat(harness): DoctorFacade orchestrator | `harness/diagnostics/inspect/inspect.py` | `lca/harness/diagnostics/doctor/facade.py` | `doctor_profile(path)->DoctorReport` 组合 P2-03…06 | integration | P2-06 | — |
| **P2-08** | feat(cli): lca-ops doctor profile | `infrastructure/cli/guide/guide.py`；`profile/inspect.py` | `commands/ops/doctor.py` | `--ci` exit 1 on error；`--json` | CLI test | P2-07 | — |
| **P2-09** | feat(harness): doctor plugin path (single module) | `harness/plugin/declaration.py` | `doctor/single_plugin.py` | AST/import 级；**不** K3 setup | unit | P2-07 | P2-08 |
| **P2-10** | test(arch): golden profiles doctor CI | `tests/golden/test_8_profiles.py` | `tests/architecture/test_0199_doctor_golden.py` | 8 profiles 零 error | arch | P2-08 | — |
| **P2-11** | refactor(web): doctor render only | `webserver/doctor/step_check.py` | web GET doctor 消费 DoctorReport shape（可选） | doctor API test | P2-07 | P2-10 |
| **P2-12** | chore(arch): HPC-L5 CI job | — | CI config / `test_0199_doctor_golden` 必跑 | CI | P2-10 | — |

**P2 禁止：** Doctor 内调用 `run_kernel` / `spawn_fiber` / `Session.append` / 网络。

---

## 6. P3 — Privilege / PluginOrigin（10 PR）

| PR-ID | 标题 | Read First | 交付 | 验证 | 依赖 |
|---|---|---|---|---|---|
| **P3-01** | feat(contracts): privileges on PluginContract | `plugin_contract.py`；ADR-0197 guard_stack | 扩展 `AuthorityContract` 或 CapabilityContract.privileges | contracts test | P2-08 |
| **P3-02** | feat(harness): project PluginSpec privilege projection | `spec_projection.py`；`declarative_plugin.py` | meta.privileges → compile | projection test | P3-01 |
| **P3-03** | feat(harness): PluginOrigin in ResolvedProfile | `resolve.py` | bundle/profile provenance | resolve test | P3-01 |
| **P3-04** | feat(harness): untrusted default disabled | ADR-0199 §3.4 | resolve 阶段 filter | HPC-L7 test | P3-03 |
| **P3-05** | feat(harness): doctor DOC-PRIV-* rules | P2 DoctorFacade | undeclared privilege finding | doctor test | P3-02 |
| **P3-06** | feat(harness): EffectPolicyPlan privilege projection | `declarative_graph.py` EffectPolicyPlan；0197 | compile 投影 | compile test | P3-02 |
| **P3-07** | feat(harness): AuditedPluginContext privilege check | `plugin/context.py` | setup fail-loud | plugin test | P3-06 |
| **P3-08** | chore(scripts): check_plugin_shape privilege audit | `check_plugin_shape.py` | HPC-L4 namespace | script + test | P3-02 |
| **P3-09** | test(arch): HPC-L6 activation_ref on sample EPs | event catalog | payload schema test | arch | P1-06 |
| **P3-10** | docs(adr): ADR-0199 Phase3 acceptance note | — | ADR 状态更新 | verify_md_links | P3-07 |

---

## 7. P4 — ResourceRegistry + PlanProposal（8 PR）

| PR-ID | 标题 | Read First | 交付 | 验证 |
|---|---|---|---|---|
| **P4-01** | feat(contracts): ResourceId namespaced | ADR-0199 §3.1 resources；0048 Skill | `contracts/runtime/resource.py` | unit |
| **P4-02** | feat(harness): ResourceRegistry compile projection | `plan_compiler.py` | compile 收集 resources 不入 executable | compile test |
| **P4-03** | feat(contracts): PlanProposal immutable | ADR-0199 §4 self-improve | `contracts/runtime/plan_proposal.py` | unit |
| **P4-04** | feat(harness): PlanProposal → compile closure | `plan_compiler.py` | 产生新 plan_ref；禁止 mutate active | integration |
| **P4-05** | test(arch): skill scan cannot register tool | `composer/skill_store.py` | I-HPC-6 gate | arch |
| **P4-06** | feat(application): proposal review port (no auto-activate) | 0187 evolve 闸 | Protocol only | contract test |
| **P4-07** | feat(doctor): DOC-RES-* orphan resource | P2 Doctor | finding | doctor test |
| **P4-08** | test(arch): PlanProposal cannot hot-swap active plan | — | I-HPC-10 | arch |

---

## 8. P5 — External Plugin Trust（6 PR）

| PR-ID | 标题 | 交付 | 验证 |
|---|---|---|---|
| **P5-01** | docs(specs): external plugin trust rubric | trust tier 文档 | verify_md_links |
| **P5-02** | feat(contracts): ExternalPluginKind enum | mcp/sandbox/worker/inprocess | unit |
| **P5-03** | feat(harness): resolve external → disabled default | profile explicit enable | resolve test |
| **P5-04** | feat(doctor): DOC-TRUST-* findings | doctor rules | doctor test |
| **P5-05** | test(arch): HPC-L8 no global tool registry | import scan | arch |
| **P5-06** | docs(adr): 0199 Accepted + delete-when 清单 | ADR 状态 | adr index test |

---

## 9. PR 级 Agent Brief 示例（P1-09，可直接复制）

```text
Task: PR-0199-P1-09 — DefaultRuntimeFacade.resolve_activation
Authority: ADR-0199 §2.2.2 SessionActivation; I-HPC-1, I-HPC-2, I-HPC-3

Read First (read in full before writing code):
  - docs/adr/0199-hermes-inspired-cognitive-plugin-convergence.md §2.2
  - lca/application/runtime/plan_resolution.py (P1-07 output)
  - lca/application/runtime/adapters/intent_from_transport.py
  - lca/contracts/runtime/activation.py
  - lca/harness/runtime/activation_ref.py
  - lca/harness/profile/resolve/resolve.py (do not duplicate logic)

Implement exactly:
  - Extend lca/application/runtime/default_facade.py
  - Class DefaultRuntimeFacade( RuntimeFacade ) with constructor-injected PlanResolutionService
  - resolve_activation(intent: RunIntent) -> SessionActivation:
      session_id = intent.session_id or generate_session_id()  # reuse existing session id helper if exists; else new util in application/runtime/session_ids.py
      plan_ref, graph_ref, plugin_set_ref, plan = self._plan.resolve_refs(intent.profile_path)
      activation_ref = compute_activation_ref(plan_ref, graph_ref, plugin_set_ref, session_id)
      return SessionActivation(..., compiled_plan=plan, trust_envelope=TrustEnvelope.empty() until P3)

Do NOT:
  - Call run_kernel, spawn_fiber, Session.append
  - Store cordis Context on SessionActivation
  - Import from lca/plugins/transport

Tests first:
  - tests/application/runtime/test_default_facade_resolve.py
      test_same_intent_same_plan_ref
      test_new_session_generates_id
      test_activation_ref_stable

Verify (all exit 0):
  uv run ruff check lca/application/runtime/ tests/application/runtime/
  uv run pytest tests/application/runtime/test_default_facade_resolve.py -q
  uv run pytest tests/golden/test_8_profiles.py -q
```

---

## 10. 设计模式与模块职责（实施时不得偏离）

| 模块 | 模式 | 职责 | 不得承担 |
|---|---|---|---|
| `contracts/runtime/*` | DTO + Protocol | 稳定 wire/意图形状 | resolve/compile/boot |
| `harness/runtime/activation_ref.py` | 纯函数 Utility | 确定性 hash | I/O |
| `application/runtime/plan_resolution.py` | Application Service | K1+K2 编排 | HTTP/CLI 解析 |
| `application/runtime/adapters/*` | Adapter | L0→RunIntent | 业务逻辑 |
| `application/runtime/default_facade.py` | Facade | L1 入口 | phase 解释 |
| `harness/diagnostics/doctor/*` | Specification + Composite | 编译期验证组合 | 修复/启动 |
| transport handlers | Adapter | bytes→RunIntent→Facade | resolve_profile |

---

## 11. COMPAT 与 delete-when 追踪

| 旧路径 | 新路径 | 引入 PR | delete_when |
|---|---|---|---|
| handler 内 `resolve_profile` | `RuntimeFacade.resolve_activation` | P1-11 | HPC-L2 grep 0 非豁免；P1-14 |
| CLI 内联 compile | facade | P1-13 | 同上 |
| `RunRequest.ctx` 为 boot SSOT | activation + kernel boot | P1-11 | ADR-0199 §12.2 .transport ctx deprecated 移除 |
| 散落 doctor 脚本 | `lca-ops doctor` | P2-08 | 脚本 README 指向新命令 |
| `LCA_RUNTIME_FACADE` 开关 | 默认 facade | P1-11 | 开关删除 + 单路径测试 |

---

## 12. 风险与 Cut-line

| 风险 | 缓解 | 可裁剪 |
|---|---|---|
| Facade 与 RunPort 双轨期过长 | P1-11 默认 facade + 开关 | — |
| 弱模型改 transport 破坏 e2e | P1-11 前先 P1-10 单测 + golden | — |
| Doctor 与 inspect-tree 重复 | P2-07 复用函数不复制 | P2-09 可延后 |
| P3 privilege 与 0197 冲突 | P3-06 单 PR 对齐 EffectPolicyPlan | P4 可整轨延后 |
| 52 PR 过多 | P1+P2 MVP 24 PR 先 ship | P5 可最后 |

**推荐交付节奏：**

1. **Sprint A（Week 1–3）：** P1 全轨 → 入口统一
2. **Sprint B（Week 4–6）：** P2 全轨 → doctor CI
3. **Sprint C（Week 7+）：** P3→P5 按 Lane G

---

## 13. 维护

- 每合并 PR：在本表 PR-ID 列追加 `Done` 标记（或 GitHub Project）
- 新增 PR 必须含：Read First、Verify 命令、不变量 ID
- 产品能力（0200.x）写入 [0200-implementation-plan.md](0200-implementation-plan.md)，**不得**塞入本表
- 权威架构：[ADR-0199](../adr/0199-hermes-inspired-cognitive-plugin-convergence.md) · [platform-directory-architecture.md](platform-directory-architecture.md)
