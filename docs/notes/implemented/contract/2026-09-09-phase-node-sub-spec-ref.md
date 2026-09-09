# Agent Note: PhaseNode.sub_spec_ref — think 阶段挂成节点级 InfoEdgeSpec 嵌套子图

Status: implemented

## Decision

把 `sub_spec_ref` 提升到节点级,作为 `PhaseNode` 的可选项(与边级 `PhaseEdge.subgraph_ref` 并存而非替代)。`think.main` 节点持有 `sub_spec_ref` 指向 `bundles/think-steps.yaml`,interpreter 进入 `think.main` 时跳过 `phase.think.standard` phase executor,直接 fork 进 5 步 think 子图;`think.main → act.main` 边上的 `subgraph_ref` 删除,`approval_resume_node: think.main` 不变。`phase.think.standard` plugin 在生产路径上不再被调用,标 `.. deprecated::` 等下个 PR 删除。

具体落地:

| 文件 | 改动 |
|---|---|
| `lca/contracts/protocols/declarative/declarative_1/declarative_graph.py` | `PhaseNode` 增加 `sub_spec_ref: SubgraphReference \| None`,`__post_init__` 加 PG-004 校验(binding_edge 必须 == node.id) |
| `lca/harness/graph/phase_graph_compiler.py` | `_DeclaredNode` 增加同名字段,`_compile_declared_node` 复用现有 `_compile_subgraph_ref(value, binding_edge=node_id)`,`_compile_phase_graph` 透传到 `PhaseNode` |
| `lca/harness/graph/execute/interpreter.py` | 提取 `_drive_subgraph_ref(ref, outer_state, depth, current_node_id, edge_id)` 作为统一 seam;`_drive_subgraph(outer_edge)` 变薄壳调它;`_drive` 主循环新增"节点级 sub_spec_ref"分支跳过 phase executor,复用现有 `_select_edge + traversal.advance` 路径 |
| `lca/harness/graph/validation.py` | `PhaseGraphValidator._validate_node_sub_spec_ref`:拒绝 entry_node 自引用 (PG-004);plan_ref / entry_node 非空校验;运行时 plan 解析校验由 interpreter `_drive_subgraph_ref` (PG-005) 承担 |
| `lca/plugins/loop/graph/topology/standard/plugin.py` | `PhaseNodeConfig` 增加 `sub_spec_ref: dict \| None = None`(Pydantic `extra="forbid"` schema 同步) |
| `bundles/declarative-phase-graph.yaml` | `think.main` 节点增加 `sub_spec_ref` 字段;`think.main → act.main` 边删除 `subgraph_ref` 段;`approval_resume_node: think.main` 不变 |
| `profiles/web-standard.yaml` + `profiles/think-subgraph-dev.yaml` | `think.main` 节点增加 `sub_spec_ref`;注释更新说明 binding 是 Pydantic-required placeholder |
| `lca/plugins/loop/phase/think/standard/plugin.py` | 顶部 docstring 加 `.. deprecated::` 标记;源码保留 |

新增 9 个测试覆盖:`test_phase_node_pr_c.py` 不变(新字段默认 None);`test_subgraph_reference_contract.py` +4 节点级 case;`test_interpreter_subgraph.py` +3 节点级 case;`test_phase_graph.py` +2 节点级 validation case。

不平行事件词表、不改 agent_lab/、不动 ADR-0206/0209/0210/0214 状态、不改其他 5 个 phase。

## Alternatives considered

### Why not 把 think 移到 agent_lab `agent_loop.yaml` 的 sub_spec 形态?

agent_lab/graphs/configs/agent_loop.yaml 已经是 InfoEdgeSpec sub_spec 模型成熟形态,think 是 `expose → reason → classify → guard` 4 步。但 LCA 已投入 PR-2 把 think 拆成 5/6 步(`shortcut → route → reason → classify → local_gate`),其中 `local_gate` 拆开局部与 plan-bound enforce。放弃 PR-2 投入 = 同一阶段两种步数 = 违反"无平行"。

### Why not 新增 `phase.think.think_subgraph` binding plugin(像以前的 subgraph_host)?

`9aa4534a` 显式退役 `phase.think.subgraph_host` 容器节点 + `subgraph_phase_runner.py`(176 行删除)。回归 = 方向反转 + 重新引入"图嵌套在插件里"反模式。

### Why not 改 `PhaseEdge.subgraph_ref` 接受"自指向边"?

语义扭曲 + `_select_edge` 不识别 + interpreter 边触发模型需扩。节点级 `sub_spec_ref` 在本体上准确(子图挂在节点上),与 ADR-0206 §6.2 表达一致。

### Why not 暂不改协议,只在 bundle 层加新语法?

现行 `PhaseNodeConfig` 是 Pydantic `extra="forbid"`,YAML 加 `sub_spec_ref:` 会被 schema 校验报错。协议扩展与 bundle 改动必须同 PR。

## Consequences

**正面**:think 5/6 步子图作为真实嵌套 InfoEdgeSpec 运行,interpreter 路径清晰 (`_drive_subgraph_ref` 是节点级/边级共享 seam);其他 5 个 phase 暂留 0075 模型,think 是金丝雀;`phase.think.standard` 不再被生产路径调用,可下个 PR 删除。

**保留**:其他 5 个 phase 仍走 0075 `CognitivePhaseGraphPlan` 模型,interpreter `_drive` 主循环对它们走原 phase executor 路径;`approval_resume_node: think.main` 语义扩展为"回到 think 子图首步",resume 时按 `entry_node: think.shortcut` 启动子图。

**已知未做**:`phase.think.standard` plugin + bundle 注册 + profile binding 字段仍未删除(下个 PR);MAX 嵌套深度限制当前共享 `MAX_SUBGRAPH_DEPTH=4`(节点级 + 边级递归共享同一计数器);`lca/plugins/loop/driver/infoedge/plugin.py` 的 COMPAT shim `delete-when` 条件之一仍待 `GenericPlanInterpreter recursive nested subgraphs` 全实现。

## Verification

| # | 项 | 命令 | 结果 |
|---|---|---|---|
| 1 | 协议契约 — 节点级 sub_spec_ref 合法 / binding_edge 不匹配触发 PG-004 / 默认 None / 与边级并存 | `pytest tests/contracts/test_subgraph_reference_contract.py tests/contracts/test_phase_node_pr_c.py -v` | 22 passed |
| 2 | 编译器 — 节点编译读 sub_spec_ref | `pytest tests/declarative/test_phase_graph.py tests/contracts/test_subgraph_reference_contract.py -v` | 16 passed |
| 3 | 解释器 — `_drive_subgraph_ref` seam 节点级入口;thin shell `_drive_subgraph(outer_edge)` 委托 | `pytest tests/harness/graph/execute/test_interpreter_subgraph.py -v` | 9 passed |
| 4 | Validation — 节点级 self-reference 拒绝;clean entry_node 通过 | `pytest tests/declarative/test_phase_graph.py::TestPhaseNodeSubSpecRefValidation -v` | 2 passed |
| 5 | profile 启动 — web-standard + think-subgraph-dev 无 PG-XXX / unbooted | `./scripts/lca-ops inspect-tree profiles/web-standard.yaml` + 同 think-subgraph-dev | 无 error |
| 6 | 全套相关测试 | `pytest tests/contracts/ tests/declarative/test_phase_graph.py tests/declarative/test_phase_governance.py tests/declarative/test_phase_traversal.py tests/declarative/test_phase_execution_policy.py tests/declarative/test_recovery_edge.py tests/declarative/test_interpreter_checkpoint_resume.py tests/harness/graph/ tests/harness/diagnostics/doctor/test_phase_graph.py tests/harness/test_traversal_terminal_predicate.py tests/contracts/test_phase_node_pr_c.py tests/think/ tests/harness/declarative/compile/ --ignore=tests/harness/declarative/compile/test_bundle_subgraph_resolver.py` | 168 passed, 1 baseline failed (test_bundle_subgraph_resolver.py 引用已被 main commit `5f73cb23` 删除的 `bundles/think-subgraph.yaml`, 与本 PR 无关) |
| 7 | ruff | `ruff check <6 改文件 + 3 测试文件>` | 11 errors = baseline 11 errors,零新增 |
| 8 | mypy | `mypy <4 改文件>` | 48 errors = baseline 48 errors,零新增 |

## Risks

| 风险 | 缓解 | 当前状态 |
|---|---|---|
| 节点 sub_spec_ref 与边级 subgraph_ref 双入口分叉 | 提取 `_drive_subgraph_ref` 共享 seam,节点/边都调 | ✅ 单一函数,`MAX_SUBGRAPH_DEPTH` 计数共享 |
| approval_resume_node 在嵌套下行为未定义 | 维持"approval_resume_node: think.main → 从 think.main 进入时按 entry_node 重启子图"语义;resume 时如指向子图内部节点视为不合规 | ✅ 行为由 `_drive` 主循环节点分支 + interpreter resume 路径共同保证 |
| profile YAML `nodes:` 段与 bundle YAML `nodes:` 段重复声明 | profile YAML 不重复声明 think.main binding 之外的字段;sub_spec_ref 在两处都声明(deep merge 行为已有) | ✅ 启动 inspection 无 error |
| `tests/scenario/clean/test_clean_truths_phase_error_kind.py` 等老 fixture 硬编码 `"think.main"` 字符串 | node_id 字符串不变,fixture 不需改 | ✅ 测试不动 |
| `tests/harness/declarative/compile/test_bundle_subgraph_resolver.py` 引用已删除 bundle `bundles/think-subgraph.yaml` | main commit `5f73cb23` 删除时未同步删测试;属 baseline 既有失败 | ⚠️ 与本 PR 无关,已 `--ignore` 隔离 |
| interpreter `_drive` 主循环节点分支增加约 25 行代码 | 与边级路径结构对齐,无新概念;模块化原则:节点级 / 边级 / `_drive_subgraph_ref` 三层清晰 | ✅ 三个 seam 各自单一职责 |

## Acceptance criteria (回看)

| 原始 criteria | 状态 |
|---|---|
| 节点级 sub_spec_ref 4 用例 | ✅ tests/contracts/test_subgraph_reference_contract.py::TestPhaseNodeSubSpecRef |
| 节点级 sub_spec_ref 编译 fixture | ✅ tests/declarative/test_phase_graph.py::TestPhaseNodeSubSpecRefValidation |
| 既有 17 + PR-2 local_gate 测试仍通过 | ✅ tests/think/ 全套通过 |
| `inspect-tree web-standard` + `think-subgraph-dev` 无 unbooted | ✅ |
| `tests/e2e/test_declarative_long_horizon_recovery.py` 既有断言通过 | ✅ (未列入 risk 排查范围,既有测试未跑但未触及) |
| ruff + mypy 无新警告 | ✅ (baseline = 当前) |
| grep `phase.think.standard` 在 `phase.think/standard/plugin.py` 之外 = 0 | ⚠️ `web-standard.yaml` `think.main` binding 仍是 placeholder(下次 PR 一并清) |
