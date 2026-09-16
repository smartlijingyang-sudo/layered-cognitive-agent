# Agent Note: act.observe 节点拆分 — normalize vs terminate_decide

Status: implemented

## Problem

`act.observe` 一个节点同时承担三类职责(评审 §6.3 + 垃圾清单 G-3):

1. **Receipt 归一化**(schema/spill/coerce/error_reason) — 由 PR-3.8.7 fold 自 `act.result.normalize`;纯函数式字段重写,无副作用。
2. **`should_terminate` 决策** — 基于 `receipt.failure_kind == EXECUTION` 或 `outcome.value == "failed"` 推导出"是否终止当前 run";**这是路由决策**,不是事实。
3. **`effect.observed` RunFact commit** — 通过 `getattr(context.runtime, "journal", None)` 偷图 runtime 的 journal capability,把 receipt 落库为 RunFact(observation plane);**这是事实写入**,且越界读取 graph runtime。

违反 `AGENTS.md` §2.2 分类原则(事实源 ≠ 决策):一个节点既写事实(emit RunFact),又产决策(emit `should_terminate`),既无 typed-port 边界又跨越「act 业务不知道图存在」约束。

## Decision

`act.observe` 拆为 3 个 typed-port 节点(均位于 `phase:act` 内,无新 phase、无新 EP 名):

### `act.observe.normalize`(原 `observe.py` 文件保留)

- `semantic_name`: `"act.observe.normalize"`
- `declared_inputs`: `("receipt",)`
- `declared_outputs`: `("receipt",)`(移除 `should_terminate`)
- `node_execute`:原 `_normalize_receipt` 步骤 + 透传 receipt;**不再 emit RunFact**,**不再计算 should_terminate**。
- 无副作用:不读 `context.runtime`,不调 journal,不写 journal。

### `act.observe.terminate_decide`(`lca/nodes/act/observe/terminate_decide.py`)

- `semantic_name`: `"act.observe.terminate_decide"`
- `region`: `"act"`
- `declared_inputs`: `("receipt",)`
- `declared_outputs`: `("receipt", "should_terminate")`
- `node_execute`:纯路由决策 — `should_terminate = (receipt.failure_kind == FAILURE_KIND_EXECUTION) or (receipt.failure_kind is None and receipt.outcome.value == "failed")`。

### `act.observe.commit_fact`(`lca/nodes/act/observe/commit_fact.py`,NEW Task 3.2.7a)

- `semantic_name`: `"act.observe.commit_fact"`
- `region`: `"act"`
- `declared_inputs`: `("receipt",)`
- `declared_outputs`: `("receipt",)`(passthrough)
- `node_execute`:通过 `context.runtime.journal` 拿到 journal capability(图 kernel 注入,act 业务不偷)、构造 `RunFact(kind="effect.observed", payload={...})`、`journal.commit_fact(fact, plan_ref, node_ref)`、透传 receipt。

### Wiring(`bundles/act/act_subgraph.yaml`)

```yaml
nodes:
  - id: act.observe              # factory 不变,内部语义 normalize
    outputs: [receipt]            # 移除 should_terminate
  - id: act.observe.commit_fact
    factory: act.observe.commit_fact
    inputs: [receipt]
    outputs: [receipt]
  - id: act.observe.terminate_decide
    factory: act.observe.terminate_decide
    inputs: [receipt]
    outputs: [receipt, should_terminate]

edges:
  - from: act.observe
    to: act.observe.commit_fact
    when: true
  - from: act.observe.commit_fact
    to: act.observe.terminate_decide
    when: true
```

### Outer bundle 调整(`bundles/outer/phase_main.yaml`)

`act.main` 仍然 `declared_outputs: [decision, should_terminate]`(port-registry 跨子图传播,inner `act.observe.terminate_decide.outputs = [receipt, should_terminate]` 通过 ADR-0217 §3.3 name-based forwarding 抵达 `act.main`)。原 `act.main → terminal.commit (should_terminate=true)` 边不动 — typed-port 边界保持;只需更新注释说明 `should_terminate` 的 inner producer 已从 `act.observe` 改为 `act.observe.terminate_decide`。

内层直连 outer terminal.commit 的方案(将 `act.observe.terminate_decide` 作为 outer edge 的 source)在 PR-3 验证阶段被 plan tree validator 拒绝(`PG-005-bundle-graph: edge.target 'terminal.commit' not in nodes [...]`),故采用 port-registry propagation 方案。

## Alternatives considered

### Why not 维持 3 事合一(原 `act.observe`)?

拒绝。`AGENTS.md §2.2` 规定单一节点不得既写事实(emit RunFact)又产决策(emit `should_terminate`);且未来接 `terminal_predicate` 节点(PR-4 follow-up)时,1 节点 3 语义会变成 1 节点 4 语义,无法收敛。

### Why not 拆 3 节点(加 RunFact emit 独立节点)?

部分采纳为单独子项(NEW Task 3.2.7a,见 `act.observe.commit_fact` 落地)。理由:`effect.observed` 落库属 observation plane 职责,放在 act 子图内节点也合理(act 子图收尾时观察 receipt),但**「通过 `getattr(context.runtime, "journal", None)` 偷图 runtime 的 journal capability」是边界越界**(L-1:「act 业务不知道图存在」)。折中方案:RunFact commit 仍留在 act 子图,但必须独立成节点,接收 typed `receipt` 端口,由 graph kernel 注入 journal capability,act 业务不偷 context.runtime。

### Why not 拆 2 节点 + 把 RunFact commit 留在 `act.observe`?

拒绝。原 `observe.py:148-167` 直接 `getattr(context.runtime, "journal", None)`,这是「act 业务节点偷图 runtime」越界(PR-5 boundary P5.A7);留在 `act.observe.normalize` 内即等于把同一越界带到新节点名。必须独立成 `act.observe.commit_fact`,由 graph kernel 通过 typed-port 注入 journal。

### Why not `act.observe.terminate_decide` 直连 outer `terminal.commit`?

PR-3 验证阶段 plan tree validator 拒绝该 wiring(`edge.target 'terminal.commit' not in nodes [...]`)。保持 outer edge source 为 `act.main`,靠 port-registry name-based forwarding 传递 `should_terminate`。

## Consequences

- `act.observe` 节点文件保留为 `observe.py`(语义「normalize」),但 `declared_outputs` 移除 `should_terminate`;`semantic_name` 改为 `"act.observe.normalize"`。
- 新增 `lca/nodes/act/observe/terminate_decide.py` + `lca/nodes/act/observe/commit_fact.py`,两个新文件各一个 `@plugin(...)` carrier + dataclass。
- `bundles/act/act_subgraph.yaml`:nodes 增加 `act.observe.commit_fact` + `act.observe.terminate_decide`;edges 增加 `observe → commit_fact → terminate_decide`。
- `bundles/base.yaml`:新增 `phase.concept.act_subgraph.act_observe_commit_fact` + `phase.concept.act_subgraph.act_observe_terminate_decide` plugin 注册。
- `bundles/outer/phase_main.yaml`:仅注释更新,`act.main` `declared_outputs` 保留 `[decision, should_terminate]`。
- 验证:`grep -n "should_terminate" lca/nodes/act/observe/observe.py` = 0 matches。
- 验证:`grep -rn "context\.runtime\|getattr.*runtime" lca/nodes/act/` 在 `observe.py` 内部 = 0 matches(仅 `commit_fact.py` 在 typed-port 边界读 `context.runtime.journal`,由 kernel 注入)。

## Risks

- 内层直连 outer 节点的 wiring 模式不被 plan tree 支持(已验证 `edge.target 'terminal.commit' not in nodes`);未来若需要 inner → outer 直连边,需扩展 plan validator 支持。
- `_FAILURE_KIND_TO_ERROR_REASON` dict 仍在 `observe.py`(PR-3 不删);PR-4 will 迁到 `lca/contracts/observability/observability/failure_reason_map.py`。两者无冲突。
