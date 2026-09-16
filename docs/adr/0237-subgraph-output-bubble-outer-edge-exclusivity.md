# ADR-0237 — act 子图输出冒泡 + outer 边互斥 (`gate.routing` 单消费者)

**Status:** Accepted — 2026-09-16. PR-1b of `2026-09-16-act-subgraph-tightening`.
**Status history:** Proposed (2026-09-16) → Accepted (2026-09-16) on PR review.

> **一句话**: 把 `act.approve.gate` 从 outer `bundles/outer/phase_main.yaml` 迁回 `bundles/act/act_subgraph.yaml`(spec §3.2 原位:`act.authorize → act.approve.gate → act.envelope`,副作用未发才可断);gate 的 typed `approval_routing` 端口(独立命名,与下游 `act.fanout` 的 `routing` 端口**不重名**避免 PortRegistry last-write-wins 覆盖)经 kernel-wide `PortRegistry` 冒泡为 `act.main` 的 `declared_outputs`;outer plan 拥有 `act.main.approval_routing` → `{intervene.interrupt | terminal.commit | reflect.main}` 的三条**互斥**消费边(同一 run 内 `approval_routing.next_hint` 只命中一条),由 typed `Predicate` 的 `eq` / `in` 词法保证互斥。同步把 `act.authorize` 的 `decision.extra["needs_approval"]` 偷读升级为 typed `approval_required: bool` port(本 PR 才真正产生消费者,故 dead-port 不提前发布)。`lifter._validate_approval_resume_node` 改为对 outer plan 求值(`approval_resume_node` 字段为 outer 唯一真值,见 ADR-0217 §3.3.3 + ADR-0234 §Decision 6)。

## Context

PR-1 (commit `d9deb7952`) 已把「`act.approve.gate` 缺 resume 边即 fail-loud」落地为 `lifter._validate_approval_resume_node`(per-plan check),并把 gate 留在 outer `phase_main.yaml`。PR-1 commit message 与 `tests/act/test_approve_gate_wiring_invariants.py` 注明:位置错误(spec §3.2 与 six-column-0206 M1 §2 要求 gate 在 `act.authorize` 与 `act.envelope` 之间)留待 PR-1b。

### 错位诊断(评审 §6.1 + F-1 + G-2)

`bundles/outer/phase_main.yaml:128-278` 当前 wiring:

- `act.main → act.approve.gate → {intervene.interrupt | terminal.commit | reflect.main}`
- 位置: `act.main` 完成 envelope + dispatch + observe **之后** 才进 gate

后果(已现场复现,plan 2026-09-16 §F-1):

1. 副作用已发(act.dispatch → effect.execute → 工具调用)再回放 HITL 决策 = 「不可逆决策后再次确认」反模式(spec §3.2 反例);
2. 三条 outer 边(`→ intervene.interrupt` / `→ terminal.commit` / `→ reflect.main`)虽各自 `when: ... next_hint`,但**谓词互斥性无静态守护**:同一次 run 的 `routing.next_hint` 字段为单个值,逻辑上互斥,但因 yaml 边序未与 gate 内决策耦合,若 gate 实现漂移(emit 多个 next_hint 或 `RoutingDecision.action_type` 与 `next_hint` 不一致),可能出现「同时命中 interrupt 与 reflect」的静默分裂(正是 AGENTS.md §3 C7 控制/观察分离的反例)。

### Subgraph 边界硬约束(评审 R-1)

`bundles/act/act_subgraph.yaml` 由 `lca/harness/declarative/compile/subgraph_resolver.py::_load_bundle_graph_spec` 加载,**每个节点必须声明 `factory`**(与 outer plan 走 `parse_plan_yaml` 默认 `binding=node_executor` 不同)。子图节点只能是该 subgraph 自己的 factory(act.* / effect.* 命名空间),不可声明 outer / sibling 节点(`intervene.interrupt` / `terminal.commit` / `reflect.main`)。

PR-1b 的搬运必须遵守:gate 节点移入 act_subgraph 后,gate 节点内部仍可读 `command` typed port(`ApprovalGateExecutor.declared_inputs = ("decision", "command")`),但 gate 的出边只能指向**子图内节点**(`act.envelope` 单出边,非 approve 分支不出边,让子图结束);intervene.interrupt / terminal.commit / reflect.main 这三个消费者必须挂在 outer plan 的 `act.main.routing` 上,子图不出现它们。

### 子图输出冒泡(PR-3 注释原话)

`bundles/act/act_subgraph.yaml::act.main` 当前 `declared_outputs: [decision, should_terminate]`(`phase_main.yaml:74` 同步声明),子图出口的 typed port 经 kernel-wide `PortRegistry`(`lca/framework/graph/port_registry.py::PortRegistry.exit_subgraph`)以「outer_outputs 元组字段名」为键投影到 outer caller's registry。冒泡机制已经存在(ADR-0217 §3.3.3 iron rule 1):outer-facing port 名 = inner entry 的 `outputs`/子图出口显式投影。PR-1b 不发明新机制,只把 `routing` 加入 `act.main.declared_outputs` 并验证 kernel 能透传。

## Decision

### 1. `act.approve.gate` 迁入 `bundles/act/act_subgraph.yaml`

在 `act.authorize` 之后、`act.envelope` 之前插入新节点:

```yaml
- id: act.approve.gate
  region: act
  factory: act.approve.gate
  # ADR-0237 / PR-1b: gate stays at spec §3.2 原位(authorize 之后、
  # envelope 之前)。``command`` typed port 是 optional(只在 resume
  # 重入时由 kernel 重新投影)。Outer plan 透过 ``act.main.declared_outputs``
  # 读 ``approval_routing``,实现 subgraph-output-bubble。
  # ``approval_routing`` 与下游 ``act.fanout`` 的 ``routing`` 端口**不重名**:
  # PortRegistry.merge_output 是 last-write-wins,若同名 fanout 会覆盖 gate
  # 的语义,使 outer plan 读到 fanout 的 fanout_1to1 而非 gate 的 approve_*。
  # 命名分开是 typed-port C13 的硬要求(port name 是 D1 定义点)。
  inputs: [decision, approval_required]
  outputs: [decision, approval_routing]
  config:
    emit_on_enter: [phase.intervene.gate.start]
    emit_on_exit: [phase.intervene.gate.end]
```

子图内边:

```yaml
# PR-1b / ADR-0237: gate 接入 act_authorize → approve → envelope 主路径
- from: act.authorize
  to: act.approve.gate
  when:
    kind: eq
    port: { name: approval_required }
    value: true
- from: act.approve.gate
  to: act.envelope
  when:
    kind: in
    port: { name: approval_routing, field: next_hint }
    value: [approve_skipped, approve_approved]
```

> 注:`approve_skipped`(needs_approval=false)与 `approve_approved`(command.kind=approve)同 next_node=act.envelope,故单一边谓词取 `in [approve_skipped, approve_approved]`。`approve_interrupt` 与 `approve_rejected` **不挂出边**,由 kernel 的 `select_edge` 返回 `None` → subgraph dispatch 路由到 outer 显式定义的 `act.main.approval_routing` 消费者(intervene.interrupt / terminal.commit / reflect.main),子图「让出」。

### 2. `act.authorize` 升级 typed port(去掉 metadata grep)

`ActAuthorizeExecutor.declared_outputs` 从 `("decision", "state")` 扩展到 `("decision", "state", "approval_required")`。`approval_required: bool` 是 typed DTO 字段(Decision.needs_approval 在 PR-5 已 typed),**不在 Decision 自身**(Decision 是 typed DTO,add field = 改 contract = 阻塞)。直接由 act.authorize 计算:`approval_required = decision.needs_approval and action_type == "use_tool"`(act.authorize 知道 action_type,见 PR-5 透传)。

```python
return NodeOutput(
    port_values={
        "decision": decision,
        "state": state,
        "approval_required": bool(decision.needs_approval),
    }
)
```

> **Why not on Decision?** Decision 是 ADR-0217 §3.3 D4 typed Contract,加 typed field = 跨 contract 改动 = 须独立 ADR。`approval_required` 由 act.authorize 计算(且只在 act 子图内有消费者),挂在子图 typed port 上 = 子图边界 = 本 ADR 闭环。

### 3. `act.main.declared_outputs` 加 `approval_routing`

`bundles/outer/phase_main.yaml::act.main`:

```yaml
declared_outputs: [decision, should_terminate, approval_routing]
```

`approval_routing` 由 `PortRegistry.exit_subgraph` 自动透传(inner act.subgraph 在 `act.approve.gate` 写 `approval_routing` port 后,outer kernel 经 `_outer_declared_outputs(context)` 把它读出,供 outer plan 用)。**不与 `act.fanout` 的 `routing` 重名**:`PortRegistry.merge_output` 是 last-write-wins,若同名 fanout 会覆盖 gate 的语义,使 outer plan 读到 fanout 的 `fanout_1to1` 而非 gate 的 `approve_*`(这是 spec §3.2 位置的硬要求:HITL 决策先于副作用,若被 fanout 覆盖则 HITL 等于失效)。

### 4. Outer edges 互斥消费 `act.main.approval_routing`

删除 `phase_main.yaml` 中 `act.approve.gate` 节点 + `act.main → act.approve.gate` 入边 + `act.approve.gate → {intervene.interrupt, terminal.commit, reflect.main}` 3 条出边。改为 3 条**互斥** outer 边,全部以 `act.main` 为 source,谓词只读 `approval_routing.next_hint`:

```yaml
# PR-1b / ADR-0237: act.main.approval_routing 单消费者互斥。
# approve_approved / approve_skipped → reflect.main(走 reflect 收尾);
# approve_interrupt → intervene.interrupt(等用户 Command);
# approve_rejected → terminal.commit(reject/redirect/resume-timeout 终止)。
# 三条边在同一字段上互斥;谓词由 ADR-0217 typed Predicate 保证。
- from: act.main
  to: reflect.main
  when:
    kind: in
    port: { name: approval_routing, field: next_hint }
    value: [approve_skipped, approve_approved]

- from: act.main
  to: intervene.interrupt
  when:
    kind: eq
    port: { name: approval_routing, field: next_hint }
    value: approve_interrupt

- from: act.main
  to: terminal.commit
  when:
    kind: eq
    port: { name: approval_routing, field: next_hint }
    value: approve_rejected
```

> **互斥性静态保障**: typed Predicate 的 `eq` / `in` 在同一 source node `act.main` 上对同一字段 `approval_routing.next_hint` 的取值集合 `{approve_skipped, approve_approved, approve_interrupt, approve_rejected}` 是**互不相交**的分区;`act.approve.gate.node_execute` 在 PR-5 commit `9845d564a` 已 typed `RoutingDecision.next_hint` 单值返回,不可能 emit 多个 hint,故 runtime 也保证「同一 run 只命中一条 outer 边」。这是 PR-3 的「dual-routing 同时触发」静默分裂类的根除。

### 5. `lifter._validate_approval_resume_node` 改为 outer 视角

现状(PR-1 commit `d9deb7952`):per-plan 检查,plan 内 gate + resume 边都在同 plan 才验。

PR-1b: gate 已迁入 act_subgraph,resume 边(`intervene.resume → act.approve.gate`)必须在 act_subgraph 内声明(因为 `intervene.resume` 在 act_subgraph 视为 stub 节点,见 PR-1 的 `tests/integration/test_outer_edge_fail_loud_missing_resume.py::test_approval_resume_node_edge_present_passes_lift` 已示范子图可声明 `intervene.resume` + `act.approve.gate` + resume 边)。

为让校验更明确(避免子图 stub 与 outer 节点耦合),PR-1b 在 lifter 中显式记录:`approval_resume_node` 字段为 outer 计划唯一真值,当 outer 计划含 `act.approve.gate`(未来若恢复 outer delegate 场景)或 outer 计划 `declared_outputs` 引用 `approval_routing` 来自 gate 时,必须存在跨 plan resume 路径——但**当前 outer plan 不再含 gate**,所以本 PR 把 lifter 的 fail-loud 改为「只在声明 gate 的 plan 上校验 resume 边」,且:
- 仍然 per-plan(act_subgraph 含 gate → 必须有 resume 边)
- outer plan 不含 gate → lifter skip

这条规则与 PR-1 commit message 一致,本 PR 不改 lifter 主体逻辑;只补一条注释说明 gate 已迁入子图,fail-loud 触发场景相应变化。

### 6. `intervene.resume` 在 act_subgraph 内的 stub 节点

为让 lifter 的 per-plan resume 校验通过,act_subgraph 须含 `intervene.resume` 节点 + `intervene.resume → act.approve.gate` 边(与 PR-1 acceptance 测试一致)。`intervene.resume` 在子图内是 stub(factory=intervene.resume,功能由 outer plan 的 `intervene.resume` 节点(有 sub_spec_ref)承担;kernel 在 resume 时把 outer `intervene.resume` 的 typed `decision` 输出投影进 act_subgraph 的 port registry,通过 `intervene.resume` stub 转发给 `act.approve.gate`)。

> 严格说:intervene.resume stub 是「子图 port wiring 占位」,不引入新逻辑,factory 复用 outer 的 `intervene.resume` factory(同一 plugin)。kernel 的 subgraph_entry 的 positional / name-based fallback 已支持这种 inner→outer 反射(ADR-0217 §3.3.3)。

## Consequences

### Positive

- **spec §3.2 原位**: gate 在 envelope 前,HITL 在副作用未发时断(不可逆决策未发 = 安全)。
- **AGENTS.md §3 C2 双平面**: cognition 不再「副作用后再回 cognition」;gate 属于 cognition 子图内部。
- **AGENTS.md §3 C7 控制/观察分离**: outer 不再持有 gate 控制面 stub,只剩 routing 投影消费。
- **AGENTS.md §3 C13 typed Contract**: `approval_required: bool` typed port 替代 `decision.extra["needs_approval"]` 偷读。
- **静默分裂根除**: 三条 outer 边在 `approval_routing.next_hint` 同一字段上 typed Predicate 互斥,杜绝「同 run 多次 routing」。
- **PR-1 验证矩阵保留**: `tests/integration/test_outer_edge_fail_loud_missing_resume.py` 不变;`tests/act/test_approve_gate_wiring_invariants.py` 更新断言方向。

### Negative / Risks

- **子图含 intervene.resume stub**: stub 节点无真实运行时副作用,但需要 factory 解析存在(避免 plan tree fail-loud)。已在 base.yaml 注册 `lca.nodes.intervene.resume`(`bundles/base.yaml:572` 附近),无新 factory。
- **`act.main.declared_outputs` 新增 `approval_routing`**: 是 outer-facing schema 增量,需通知所有消费 `act.main` 的 outer 边。当前 outer 只有「act.main → terminal.commit / think.main」两类消费者,均不读 `approval_routing`,无 breaking change。
- **lifter fail-loud 触发面收窄**: 仅 act_subgraph 触发;若未来 outer plan 重新出现 gate delegate,fail-loud 仍生效(per-plan 规则保留)。

### Neutral

- `tests/act/test_approve_gate_wiring_invariants.py` 的 `test_gate_declared_in_exactly_one_plan` 方向反转(inner=True, outer=False);这是 spec §3.2 的正确方向,改动与本 ADR 同步。
- `tests/intervene/test_approve_gate_phase_plugin.py::test_gate_resume_edge_is_present_in_outer_plan` 改为断言 resume 边在 `act_subgraph.yaml` 中(plan 标记为 inner)。

## Alternatives Considered

### A. Keep gate in outer + fix position by routing act.main to gate (current state, rejected)

评审已记录(rejected F-1):位置仍在 envelope 后,与 spec §3.2 不符;三条 outer 边无 typed Predicate 互斥守护。

### B. Gate inside act_subgraph, outer edges on act.main only (PR-1b design, accepted)

Gate 在 spec §3.2 原位;outer 边互斥消费 `act.main.routing` typed port;lifter fail-loud 仍 per-plan 作用于 act_subgraph。

### C. Gate as a separate subgraph (not adopted)

把 gate 提为 `bundles/intervene/approve_subgraph.yaml`,act_subgraph 通过 sub_spec_ref 引用。代价:act → intervene → act 跨 subgraph 调用图,与 ADR-0228 §3 「gate 是 region:intervene sibling subgraph 而非独立 phase」冲突,且增加一张 plan yaml。

### D. 让 outer 边直接读 act_subgraph 的内部节点 (not adopted)

违反 R-1 子图边界硬约束(`factory` 强制);outer 不能命名 `act.approve.gate`。

## Refines / Fixes

- ADR-0195 §1.4 C13 — typed Contract 跨边界 = fail-loud。
- ADR-0217 §3.3.3 — PortRegistry.exit_subgraph iron rule 1(outer-facing 字段名 → inner registry 投影),本 ADR 验证该机制已可用。
- ADR-0220 §3.3 — bundle v2 graph schema;gate 节点 yaml 形态仍合规。
- ADR-0228 §3 — gate 是 region:intervene sibling subgraph;本 PR 把 gate 从 outer 拉回 act_subgraph 内,与之不冲突(region 标签仍为 `region:act` 或保留 `region:intervene`,见 §Implementation Note)。
- ADR-0234 / ADR-0235 — typed-port 卫生的延续。

## Implementation Notes

- gate 节点 `region:` 字段保留 `intervene`(与 PR-3.8.6 + ApproveGateExecutor 一致);`region:act` 不强制(混合 region 节点允许,见 `tests/act/test_approve_gate_wiring_invariants.py` 现存设计)。
- act_subgraph.yaml 现有的 `act.fanout` / `effect.pre_dispatch.envelope_check` / `act.dispatch` / `act.observe*` 不动(本 PR 仅在 `act.authorize` 与 `act.envelope` 之间插一节点)。
- `intervene.resume` stub 在 act_subgraph 内的 factory 复用 `lca.nodes.intervene.resume`(已在 base.yaml 注册)。
- `PortRegistry.exit_subgraph` 调用方(`lca/framework/graph/strategies/subgraph_strategy.py`)透传 outer_outputs 字段名;`routing` 不在 `act.subgraph.yaml::id` 显式声明 `outputs`,而是按 SubgraphStrategy 的 name-based fallback 把 `act.main.io_schema.outputs` 包含的字段都读出来——本 ADR 已在 act_subgraph 的子图层加 `outputs: [routing]` 风格的隐式声明(若需要,在 act_subgraph 顶层 yaml 加 `outputs:` 块)。

## Acceptance

- `act.approve.gate` 节点仅在 `bundles/act/act_subgraph.yaml` 声明,不在 `bundles/outer/phase_main.yaml` 声明;
- `act.authorize.declared_outputs` 含 `approval_required: bool`;
- `act.approve.gate.declared_outputs` 含 `approval_routing: RoutingDecision`(与 fanout 的 `routing` 不重名);
- `phase_main.yaml` 含 3 条 outer 边,均 source=`act.main`,谓词在 `approval_routing.next_hint` 字段上 typed Predicate 互斥(同一 run 仅命中一条);
- `intervene.resume → act.approve.gate` resume 边迁入 act_subgraph;
- lifter fail-loud 在 act_subgraph 缺 resume 边时仍触发(per-plan 保留);
- `act_subgraph.yaml` 不声明 outer 节点(`intervene.interrupt` / `terminal.commit` / `reflect.main`);
- `plan tree profiles/web-standard.yaml` 全 inflate 通过;
- `pytest tests/act tests/intervene tests/contracts/observability tests/integration/test_no_dual_sink.py tests/effect tests/integration/test_outer_edge_fail_loud_missing_resume.py` 全绿;
- `audit-state-writers` 仍报「No state mutations detected」(本 PR 不引入 reducer / state-writer)。

## Open Questions

无(详见 PR-1b plan §5 自检)。
