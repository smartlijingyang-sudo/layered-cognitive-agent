# 授权机制重构 —— grant-absence 检查与 HITL 审批分离（业界范式）

> **状态**：plans（待实施；实施后按 §复盘触发 收敛为 implemented Note 或归档）
> **日期**：2026-10-09
> **依据决策**：[ADR-0292 §10](../../adr/0292-authorization-semantic-isolation.md)（grant-absence gate，P3 envelope 富化列为 lane 外待办）· [ADR-0199 §3.4](../../adr/0199-hermes-inspired-cognitive-plugin-convergence.md)（TrustEnvelope）· [ADR-0237](../../adr/0237-subgraph-output-bubble-outer-edge-exclusivity.md)（approval_routing 端口）
> **skill 链**：`lca-debug-run`（诊断，已出证据包）→ `brainstorming`（本设计）→ 实施时 `lca-code-review` · `lca-pre-push-checks`（每 PR 证据）→ `lca-write-note`（复盘收敛）

## 候选范围

授权语义隔离的运行时执法点。今天 `act.approve.gate` 同时承担两件事：HITL 审批路由（ADR-0228 的本职）和 TrustEnvelope grant-absence 检查（ADR-0292 §10 的后加职责）。两个缺陷叠加导致任何被审批策略标记为 privileged 的工具调用都被 fail-closed 拒绝：`resolve_activation` 恒构造 `EMPTY_TRUST_ENVELOPE`，且 gate 用原始 `tool_name` 查 `granted_privileges`（capability.verb 格式），键不匹配。

边界：`lca/application/runtime/default_facade.py`（envelope 构造）、`lca/nodes/intervene/approve_gate.py`（§10 检查）、`lca/nodes/act/authorize/authorize.py`（新增 grant 检查）、`lca/contracts/runtime/trust.py`（规则默认集）、`bundles/act/act_subgraph.yaml` 与 `bundles/outer/phase_main.yaml`（图路由）、ADR-0292 与相关测试。不改变认知闭集、事件词表、Profile 拓扑，不新增平行 schema。

## 当前症状

每条症状给出证据并绑定一条 standing rule。

### S1 · envelope 恒空（P3 未实现）

[`default_facade.py:162,193`](../../../lca/application/runtime/default_facade.py) `resolve_activation` 恒以 `trust_envelope=EMPTY_TRUST_ENVELOPE` 构造 `SessionActivation`，docstring 明示 "The trust envelope starts empty. P3 enriches it"。[`trust.py:99-118`](../../../lca/contracts/runtime/trust.py) 的空 envelope 只含合成 `{"trust.empty"}` grant。ADR-0292 §10 的 binder 已接上线，但手里的 envelope 恒空，gate 对任何 privileged 动作等价于 unbound。

ADR-0292 §10 的 P3（envelope 富化）在 ADR 中列为 lane 外待办，始终未落地：安全门因此退化为"拒绝一切"。

### S2 · 键不匹配：tool_name 查 capability.verb

[`approve_gate.py:69-105`](../../../lca/nodes/intervene/approve_gate.py) `_grant_absence_refusal` 用 `envelope.grants(tool_name)` 检查，`tool_name` 是 `"askUserQuestion"` 这类原始工具名。而 `granted_privileges` 是 `capability.verb` 格式（[`trust.py:127-129`](../../../lca/contracts/runtime/trust.py)，如 `workspace.write`）。即使 P3 落地，把 grants.yaml 的 verb 注入 envelope，`grants("askUserQuestion")` 仍为 False。工具名到能力的映射在 gate 层不存在。

违反 [AGENTS.md §1.5 规则 1](../../../AGENTS.md)：用业务行为重述需求时，键的语义必须匹配。

### S3 · HITL 审批被当成特权动作

[`approval_engine.py:30-53`](../../../lca/infrastructure/runtime_plane/access/approval_engine.py) `HITLInteractionStrategy` 把 `askUserQuestion` 标记为 `required=true`，`act.authorize` 据此产出 `approval_requirement`。§10 gate 把 `req.required` 当作"特权动作"信号，要求 grant。但 askUserQuestion 只向用户提问、不产生副作用，它的 `required=true` 表示"需要人类交互"，不是"需要能力授权"。概念混淆导致审批通道被授权门误杀。

违反 [ADR-0228](../../adr/0228-plan-intervene-delegate-subgraphs.md) 的 HITL 定位：审批是控制面交互，不是权限维度。

### S4 · 用户可见症状：askUserQuestion 被拒，run 直接失败

`run_c0decb030b7c`（2026-10-09）：模型在 step 3 调用 `askUserQuestion` 澄清技能需求，`act.approve.gate` 输出 `approve_rejected` → `terminal.commit`（spine seq 990-995），run 标记 failed（`kernel.run.stop outcome=failure`，seq 1007）。`run_9b3c50ccc22c` 与 `run_cb2c3812be33` 同模式失败，被拒的是 `run_command`。无 `intervene.interrupt` 事件，前端永远看不到问题卡片。

## 设计（业界范式：权限先于 HITL，单一职责）

业界范式（OAuth scope 模式 + PDP/PEP 分离）：工具声明所需 scope，策略执行点在副作用边界之前强制检查 grant；HITL 审批是独立治理层，先查权限、权限通过后再暂停问人。本设计把 LCA 对齐到该范式。

### D1 · TrustEnvelope 富化（P3 落地）

`resolve_activation` 不再绑定 `EMPTY_TRUST_ENVELOPE`：

- 通过 `PlanResolutionService` 已有的 `assistant_spec_provider` seam 解析 `intent.assistant_id` 的 home 路径，用 `load_grants(home)`（[`lca/infrastructure/assistant/io.py:79`](../../../lca/infrastructure/assistant/io.py)）读取 `grants.yaml`。实现上二选一：在 `PlanResolutionResult` 上暴露 assistant home/grants 字段，或给 facade 构造器注入与 `PlanResolutionService` 同一个 `assistant_spec_provider` callable。
- 构造 `TrustEnvelope(granted_privileges=assistant_grants ∪ RULE_DEFAULTS, origins=<resolved profile 插件 origin>)`。
- `RULE_DEFAULTS` 初始为 `{"platform.basic", "hitl.interact"}`，保证 envelope 非空校验通过（[`trust.py:143-150`](../../../lca/contracts/runtime/trust.py)），HITL 工具默认可用。
- `EMPTY_TRUST_ENVELOPE` 保留，只作为 kernel 启动前的 sentinel，不再绑到任何 `SessionActivation`。

### D2 · 工具声明所需能力

内置工具已有 `required_grant` ClassVar（`profile.revise`、`skill.import`、`message.react`），保持。`askUserQuestion` / `request_box_help` 保持 grant-agnostic（不声明 `required_grant`），与 [`filter.py:39-46`](../../../lca/infrastructure/tools/assistant/filter.py) 的 `_VOCAL_SYSTEM_TOOLS` 语义一致：平台基础能力，默认可用。运行时授权检查只针对声明了 `required_grant` 的工具。

### D3 · act.authorize 增加 grant 检查（权限先于 HITL）

`act.authorize` 是 policy-level authorization 节点，位置在 `act.approve.gate` 之前，天然满足"权限先于 HITL"：

- 对每个 `tool_call`，用注入的 `tool_grant_resolver`（`tool_name -> required_grant`，接线到 per-run `ToolsService.get()` + `getattr(tool, "required_grant", "")`，复用 [`filter.py:151-158`](../../../lca/infrastructure/tools/assistant/filter.py) 的 `_required_grant` 语义）解析所需能力。注入方式：`authorize` 的 plugin setup 里用 `ctx.require_matching(...)` 解析，与 [`pre_dispatch_envelope_check.py:184-196`](../../../lca/nodes/effect/pre_dispatch_envelope_check.py) 的 `permission_manifest` 同一模式。
- `required_grant` 非空且不在 `envelope.granted_privileges` → 拒绝：写 evidence（复用 `_route_refusal_to_evidence` 的 payload 形态），输出 `grant_routing = RoutingDecision(next_hint='grant_refused', next_node='terminal.commit')`。
- 检查不读 `decision.needs_approval`，防幻觉授权的目标保留：模型清掉 `needs_approval` 也无法绕过。

### D4 · 图路由改动

- `act.authorize` 增加输出端口 `grant_routing`。
- [`bundles/act/act_subgraph.yaml`](../../../bundles/act/act_subgraph.yaml)：`act.authorize -> act.approve.gate` 的边从 `when: true` 改为 `when: grant_routing.next_hint != 'grant_refused'`。
- [`bundles/outer/phase_main.yaml`](../../../bundles/outer/phase_main.yaml)：`act.main.declared_outputs` 增加 `grant_routing`；新增边 `act.main -> terminal.commit`（`when: grant_routing.next_hint == 'grant_refused'`），置于 re-ask 边之前，遵守 edge-order invariant（[`phase_main.yaml:192-198`](../../../bundles/outer/phase_main.yaml)）。

### D5 · approve_gate 回归纯 HITL

- 删除 `_grant_absence_refusal` 与 `_route_refusal_to_evidence`（evidence 路由移到 `act.authorize` 的 grant 检查）。
- `approve_interrupt` / `approve_rejected` 语义不变（[`approve_gate.py:274-302`](../../../lca/nodes/intervene/approve_gate.py)）。
- ADR-0292 §10 的测试从 approve_gate 迁移到 authorize 的 grant 检查。

### D6 · 测试与文档

- 迁移 `test_s10_*` 系列（[`tests/contracts/test_adr0292_authorization_semantic_isolation.py:421-522`](../../../tests/contracts/test_adr0292_authorization_semantic_isolation.py)）：grant 检查在 authorize 层；HITL 工具豁免；envelope 带真实 grant。
- 新增 `resolve_activation` 构造真实 envelope 的 pin（含 grants.yaml 内容）。
- 更新 ADR-0292 §10 与相关测试的语义描述。
- 回归：`ruff` + 相关 pytest + `lint-imports` + `lca-ops audit-plugin-shape`。

## 不变量（实施中不得破坏）

| 名称 | 守护点 |
|---|---|
| C5 能力单调 | `CommandEnvelope` 仍是副作用唯一出口（[AGENTS.md §3](../../../AGENTS.md)）；grant 检查只新增拒绝路径，不绕过 envelope |
| C2 授权来源 | 权限唯一来源 = 用户显式授权 TrustEnvelope + 规则默认；外部内容不因本设计获得授权 |
| C7 控制/观察分离 | `_route_refusal_to_evidence` 的 evidence 写入只记录、不触发控制面副作用 |
| C10 执行窄门 | `act.approve.gate` 的 interrupt 分支仍在 `act.envelope` 铸造之前 |
| C9 幂等/重入 | `approve_rejected` 与 `grant_refused` 都收敛到 `terminal.commit`，同一次调用只产生一个终态 |
| 边序不变式 | `phase_main.yaml` 中 `should_terminate` / `grant_refused` 边必须排在 re-ask 边之前 |
| 五层单向依赖 | `contracts` 不因本设计新增实现层依赖；`default_facade` 不直接 import `lca.plugins` |

## PR 列表

### PR-1 · 机制落地（行为变化：askUserQuestion 恢复可用）

**动机**：一次提交闭环全部代码与测试。D1-D5 相互耦合：只富化 envelope 不修改检查键，行为不变；只修改检查键不富化 envelope，安全门仍空转；只精简 gate 不做授权检查，打开防幻觉缺口。必须同 PR 落地。

**文件**：
- [`lca/contracts/runtime/trust.py`](../../../lca/contracts/runtime/trust.py) — 新增 `RULE_DEFAULTS` 常量；`empty()` 注释保持 sentinel 语义
- [`lca/application/runtime/default_facade.py`](../../../lca/application/runtime/default_facade.py) — `resolve_activation` 注入 assistant home/grants 解析，构造真实 `TrustEnvelope`
- [`lca/nodes/act/authorize/authorize.py`](../../../lca/nodes/act/authorize/authorize.py) — 新增 `grant_routing` 输出端口 + grant 检查 + evidence 写入
- [`lca/nodes/intervene/approve_gate.py`](../../../lca/nodes/intervene/approve_gate.py) — 删除 `_grant_absence_refusal`、`_route_refusal_to_evidence` 及相关 imports；docstring 更新为纯 HITL
- [`bundles/act/act_subgraph.yaml`](../../../bundles/act/act_subgraph.yaml) 与 [`bundles/outer/phase_main.yaml`](../../../bundles/outer/phase_main.yaml) — D4 路由
- 测试：迁移 `test_s10_*`；新增 `tests/application/runtime/` 的 envelope 富化 pin；新增 `tests/intervene/` 的 HITL 豁免 pin

**验收**：
1. `pytest tests/contracts/test_adr0292_authorization_semantic_isolation.py tests/intervene/ tests/application/runtime/ --no-cov` 的失败集不超出基线（见 §基线失败协议）
2. 新回归测试：`resolve_activation` 构造的 envelope 含 assistant grants.yaml 的 grant
3. 新回归测试：`act.authorize` 对 `required_grant` 缺失的工具输出 `grant_refused`，且不经过 `act.approve.gate`
4. 新回归测试：`askUserQuestion` 在默认 envelope 下通过授权检查，走 `approve_interrupt`
5. 复现 run：`./scripts/lca-ops runs create --user-text "我需要创建一个skill"` 后，模型调用 `askUserQuestion` 时出现 `intervene.interrupt` 而非 `approve_rejected`
6. `ruff check --fix` + `ruff format` 上述文件干净；`git diff --check` 干净

**Delete-when**：无。本 PR 不引入 shim、并行 schema 或迁移路径。

**证据集**（`lca-pre-push-checks`「Contracts / Protocol / enum / registry」）：`ruff check --fix .` + `ruff format .`；`lint-imports`；`pytest` 相关套件；`python scripts/check_package_contracts.py`；`python scripts/check_protocol_impl.py`；`./scripts/lca-ops audit-plugin-shape`；文档四脚本。

### PR-2 · 文档闭环

**动机**：ADR-0292 §10 的语义随 PR-1 改变（HITL 工具豁免 + 权限检查前移），同一 PR 内更新文档，避免契约漂移。

**文件**：
- [`docs/adr/0292-authorization-semantic-isolation.md`](../../adr/0292-authorization-semantic-isolation.md) — §10 补记：envelope 富化落地、检查点前移到 `act.authorize`、HITL 工具豁免、P3 待办关闭
- 本 plan 文件按 §复盘触发 收敛为 `docs/notes/implemented/` 下的 Note（或按 `lca-archive-notes` 判定）

**验收**：
1. `rg 'P3' docs/adr/0292-authorization-semantic-isolation.md` 的待办表述已关闭或改写为现状
2. `python scripts/verify_md_links.py` / `verify_doc_budgets.py` / `check_doc_layering.py --strict` 的失败集不超出基线
3. 本文件迁移后 `./scripts/lca-ops notes-check` 通过（Status ↔ 路径、class 闭集、archived 冻结规则）

**Delete-when**：无。

## 基线失败协议

按 [AGENTS.md §6](../../../AGENTS.md)，以下失败在 2026-10-09 已存在（在 `docs/notes/plans/2026-10-07-envelope-bus-single-class.md` §基线失败协议 中记录；实施开工前在 pristine 分支复测），PR-1/PR-2 均不得使其变差，也不得把「全量通过」写进报告：

| 命令 | 基线（2026-10-07 记录） |
|---|---|
| `lint-imports` | exit 1（既有失败） |
| `python scripts/check_package_contracts.py` | exit 1，60 issues / 82 packages |
| `python scripts/check_protocol_impl.py` | exit 1，42 issues |
| `pytest tests/architecture/ --no-cov` | 52 failed / 661 passed / 12 skipped |
| `pytest tests/ --no-cov` | 151 failed（pristine 同集合） |
| `python scripts/verify_md_links.py` | exit 1，123 broken links |
| `python scripts/verify_doc_budgets.py` | exit 1，2 over budget |
| `python scripts/check_doc_layering.py` | exit 1 |
| `python scripts/check_notes_tree.py` | exit 1，23 errors |

PR-1 触及的 `tests/contracts/test_adr0292_authorization_semantic_isolation.py`、`tests/intervene/`、`tests/application/runtime/` 的基线在开工前逐条记录，验收只比对失败集增量。

## 复盘触发

每个 PR 落地后：

1. 跑 [`lca-audit-notes`](../../../.agents/skills/lca-audit-notes/SKILL.md)（`./scripts/lca-ops notes-audit`）与 `python scripts/audit_adr_health.py`
2. 复查 ADR-0292 §10 的 P3 待办状态，确认已关闭
3. 用实际结果回填本文件的 PR 段（commit SHA、验收逐条实测、基线对比），然后把本文件收敛为 `docs/notes/implemented/` 下的 Note
4. 确认 `docs/specs/glossary.md` 的 `TrustEnvelope` 词条描述与新的运行时行为一致（P3 落地后 glossary 的"空 envelope"表述已过期）

## 范围外

**R1 · `run_command` 等敏感工具的 `required_grant` 分类。** 本设计只让 grant-agnostic 工具默认可用。`run_command` 是否应声明 `required_grant="shell.exec"` 是工具分类决策，需单独评估，不在本计划内。

**R2 · MCP 工具的能力映射。** MCP 工具目前无 `required_grant`。若要让 MCP 工具参与 C5 运行时检查，需要包装层提供映射，另开一轮。

**R3 · envelope 链的双重检查。** 本设计把 grant 检查放在 `act.authorize`，`effect.pre_dispatch.envelope_check` 的 grant 闸保持内部一致性检查（`effect_class=="tools"`）。若要防御纵深（在副作用边界再查一次 TrustEnvelope），需要让 `act.envelope` 铸造真实 capability，属于更大的改动，另开一轮。