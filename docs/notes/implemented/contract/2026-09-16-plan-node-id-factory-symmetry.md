# Agent Note: Plan node `id` ↔ `factory` symmetry is boot-checked

Status: implemented

## Problem

BundleGraphSpec 节点声明两个独立字段:`id`(plan 内引用名)与 `factory`(lifter 用来解析 `BindingKind.NODE_EXECUTOR` 的工厂字符串)。Run 时由 `make_node_executor_lookup` 用 `node_id` 在 `node_executors` 注册表里查 executor;该注册表的 key 由 plugin `provides="<region>::<factory>"` 的尾段(即 `factory` 名)产生。

当 `id` 与 `factory` 不一致时,boot 校验 `check_node_executor_coverage` 只验 `factory → plugin` 关系(通过);run 阶段用 `id` 查注册表找不到 → `RuntimeError("NodeExecutor lookup miss")`。此次具体样本:`bundles/think/think_subgraph.yaml` 中 `think.llm.invoke` 节点声明 `factory: llm.invoke` —— factory 在 plugin `provides="think::llm.invoke"` 里有 provider,boot 通过;run 阶段 `node_executors.get("think.llm.invoke")` 返回 None,运行在 `think.main → think.llm.invoke` 处崩,根因(`run_cb35e39f1e39`,broken_hop=H6)。

`bundles/think/think_subgraph.yaml` 内其它 12 个 leaf 节点的 `id` 与 `factory` 字符串恰好相等(`think.shortcut` ↔ `think.shortcut` 等),所以巧合通过。本 Note 关闭的是**这层未声明的对称性约束**——约束只存在于作者下意识,而代码没有 enforce。

## Decision

### D1 — 修当前漂移:`think.llm.invoke` / `think.llm.persist` 的 `id` 与 `factory` 对齐

`bundles/think/think_subgraph.yaml` 这两个 leaf 节点的 `id` 改为与 `factory` 同字符串(`llm.invoke` / `llm.persist`);同步修改三处 edges 与一处 comment(行 100 的 "Spec §D" 描述)。`bundles/base.yaml` 顶层 plugin 注册条目 `phase.think.llm.invoke` / `phase.think.llm.persist` 不动——那是 plugin id(`lca.nodes.think.llm.invoke` 模块身份)而非 NodeExecutor 注册 key,与本 Note 不在同一命名空间。

### D2 — boot 校验扩展 `check_node_executor_coverage`,加 ID ↔ factory 对称性规则

在 `lca_kernel/boot/plan_validation/checks/node_executor_coverage.py` 内,对每个 leaf 节点(非 subgraph delegate)额外断言:`node.id` 与 `node.factory` 字符串**逐字节相等**。不满足时报 `PlanLiftError`,message 同时指明 `node.id` 与 `factory`,提示把 `id` 改成与 `factory` 一致。

为什么是逐字节相等而非"末段切分后比较":runtime `make_node_executor_lookup` 用 `node_id` 在 `node_executors` 字典里查,而 `node_executors` 的 key 由 `resolve_node_executor_bindings` 写入为 plugin `provides="<region>::<factory>"` 的尾段(即 factory 字符串本身)。如果允许 `id` 末尾切分后比较,把 `id="think.llm.invoke"` 当成"末段 `invoke` 等于 factory `llm.invoke` 的子串"会变成错误通过——而真实 lookup 用 `think.llm.invoke` 当 key 仍然 miss。`bundles/think/think_subgraph.yaml` 内其它 12 个 leaf 节点的 `id` 已逐字节等于 `factory`(都是 `think.shortcut`、`think.route.decide` 等),所以"逐字节相等"是当前既有事实约束,不是新引入的。

### D3 — 测试矩阵(`tests/lca_kernel/boot/test_node_executor_coverage_check.py`)

新增三条测试:

1. `test_node_id_factory_mismatch_rejected` —— 节点 `id="think.llm.invoke"` 但 `factory="llm.invoke"`(实际漂移样本),plugin provides=`think::llm.invoke`,期望返回 1 个 `PlanLiftError`,message 同时包含 `node_id` 与 `factory`。
2. `test_node_id_equals_factory_passes` —— 节点 `id="llm.invoke"`,`factory="llm.invoke"`,plugin provides=`think::llm.invoke`,期望 0 errors。
3. `test_node_id_mismatch_does_not_mask_missing_factory_error` —— 节点 `id="orphan.id"`,`factory="other.thing"`,plugin provides=`think::think.shortcut`,期望 1 个 error(且是 factory-missing 错误,不是 ID 对称性错误)。

既有三条测试(`missing_factory_rejected_with_clear_message` / `provided_factory_passes` / `subgraph_delegate_with_config_sub_spec_ref_is_not_a_leaf`)保持不变。

### D4 — `ResolvedPlugin.id` 与 `provides=` 关系保持现有 SSOT

遵循 [2026-09-16-region-prefix-ssot.md §D5](./2026-09-16-region-prefix-ssot.md):`resolve_node_executor_bindings` 仍按 `key.rsplit("::", 1)[-1]` 取 factory 名,不读 region 前缀。本 Note 不动 runtime lookup 路径,只在 boot 校验层加一条规则。

### D5 — Delete-when

boot 校验里的 ID ↔ factory 对称性检查在以下任一条件满足时**与本 Note 同 PR 删除**:

1. lifter 升级到只接受 `factory` 作为唯一 ID 源(`node.id` 由 lifter 从 `factory` 自动派生或被废弃),runtime lookup 用 `factory` 当 key;
2. 或 plan schema 升级到 v3,要求 `id == factory`,author-time 由 yaml schema 强制(`additionalProperties` + pattern),boot 校验冗余;
3. 或 runtime `make_node_executor_lookup` 改成"先按 `node_id` 查,miss 时按 `node_id.rsplit(".", N)[-1]` 兜底",那 ID 末段对称性由 runtime 自己覆盖。

未触发条件前,本校验是唯一 fail-loud 防线。

## Consequences

### 已落地的代码改动

- **`bundles/think/think_subgraph.yaml`**:`think.llm.invoke` → `llm.invoke`,`think.llm.persist` → `llm.persist`,以及三处 edges(`history.assemble → llm.invoke`、`llm.invoke → llm.persist`、`llm.persist → decision.parse`)与一行注释同步。
- **`lca_kernel/boot/plan_validation/checks/node_executor_coverage.py`**:在 `check_node_executor_coverage` 末尾追加一条 leaf 检查分支;错误消息明确指出 `node.id` 末段不等于任一 provided factory 的事实。
- **`tests/lca_kernel/boot/test_node_executor_coverage_check.py`**:新增三条测试(见 D3)。

### Trade-off

- **boot 校验代码路径多一条分支**:单 plan 校验 O(n) → O(n),无运行时影响(boot 期)。
- **未来 plan 作者自由度收紧**:写一个 `id` ≠ `factory` 的 leaf 节点会被 boot 拒。这是有意为之——这种不一致是当前 bug 的唯一来源。
- **未覆盖 subgraph delegate 节点**:有 `sub_spec_ref` 的节点是 outer alias,内层 plan 走独立校验;本 Note 不动这条边界(既有 test_subgraph_delegate_with_config_sub_spec_ref_is_not_a_leaf 守住)。

## Alternatives considered

### Why not auto-derive `node.id` from `factory` at lift time?

让 lifter 在 `id` 与 `factory` 不一致时**自动用 factory 覆盖 id**——能让现有 yaml 不改就工作。Rejected:lifter 静默改写 plan 字段违反 "lifter 是无副作用映射"的契约(见 ADR-0217 Bundle Graph Schema v2);且会让 author 写的 ID 注释(例如 `Spec §C persist-before-execute split` 描述行 117-121)与实际节点对不上。

### Why not require `id == factory` strictly (no suffix split)?

这是当前实现(见 D2)。拒绝任何放宽到"末段切分"或"包含关系"的理由:runtime `make_node_executor_lookup` 用 `node_id` **完整字符串**当 key,不存在任何归一化逻辑。允许末段切分等于让 boot 校验与 runtime 行为再次漂移——本次 bug 的根因之一就是两端语义不一致。本 Note 的策略是"boot 强制与 runtime 完全一致",而不是放宽 boot 校验。

### Why not validate at lift time per-plan rather than boot time?

`check_node_executor_coverage` 已在 boot pre-lift 阶段执行——目的是比"运行到中段才崩"更早 fail-loud,且不依赖运行时 interpreter 跑过该路径。新增规则放同一函数避免引入第二个校验器、双重失败信号、读数混乱。

### Why not add a yaml schema validator (`additionalProperties: false`)?

yaml schema 层强制是 D5 delete-when 路径之一;现阶段 boot 校验足够且不引入新依赖(jsonschema)。等 plan schema 升级到 v3 再切。

## Testing

- **新增 3 个测试**:`tests/lca_kernel/boot/test_node_executor_coverage_check.py` 中 D3 列出的三条。
- **回归**:既有 3 条测试保持不变;`bundles/think/think_subgraph.yaml` 修改后手测 `lca-ops kernel_check profiles/web-standard.yaml` 通过;重跑 `run_cb35e39f1e39` 同 user-text 不再 `NodeExecutor lookup miss`(`think.llm.invoke` 节点正常走到 `llm_response` 输出)。
- **全量**:`./scripts/lca-ops kernel-restart` 自带 `boot_check` + `fiber_report` + `health_probe` 三步必须全 OK。

## Related

- [2026-09-16-region-prefix-ssot.md](./2026-09-16-region-prefix-ssot.md) —— region 前缀 SSOT(同日落地,本 Note 引用其 §D5 runtime 不变)
- ADR-0217(Bundle Graph Schema v2)—— bundle yaml 形态定义;`node.id` / `node.factory` 两字段语义
- ADR-0231(region prefix SSOT)—— region 命名空间与本 Note 的 factory 命名空间正交
- `lca_kernel/boot/plan_validation/checks/node_executor_coverage.py` —— 本 Note §D2 的改动目标文件
- `bundles/think/think_subgraph.yaml` —— 本 Note §D1 的改动目标文件
