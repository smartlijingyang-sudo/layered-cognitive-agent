# Agent Note: inner→outer subgraph close-out 字段名 SSOT 收敛

Status: implemented
ADR: docs/adr/0219-phase-graph-unification.md §10.11.5

## Problem

`lca/framework/subgraph/plugins/channel.py` 的 `PhaseOutput` 写死 4 个字段定义,4 字段名又被 3 处分别字面化:
- `node_graph_driver.py` 内联元组循环
- `driver_signal.py` `port_values.get("decision")` 等四行(纯函数)
- `channel.py` `absorb` merge 逻辑里的 `self._last("decision")` 等四行

三处同根,共同暴露 `lca/framework/subgraph/`(`infrastructure` 层)在三处分别认得 cognition 层 phase artifact 字段名。三个独立问题:

1. **边界穿透**。AGENTS.md §2.1 单向层契约:`subgraph/` 不得反向"知道" cognition 字段名。当前代码用字面量规避 `import`,但语义依赖 = 边界穿透。
2. **SSOT 假象**。`PhaseOutput` 在 `channel.py` 声明 4 字段定义,但 close-out 协议真正定义在 driver + driver_signal + channel 三处 —— 字段集合是隐式协议,改一处忘另一处 = silent behavior drift。**根因不是图驱动脱钩,而是 `PhaseOutput` 字段集没有 typed fold 表达**。
3. **数据被当控制流用**。AGENTS.md §1.5 §5「数据优于控制流」:字段名应是 `CLOSE_OUT_FIELDS` 元组 / 注册表,不是 `for` 循环 / `getattr` 链 / Pydantic 字段定义里的字面控制流目标。

ADR-0219 §5.1 已把 4 个字段名放进 `PortName` Literal 闭集,但 §10.11 未触及 `node_graph_driver.py:236` 与 `driver_signal.py` 与 `channel.py` —— 闭集约束了"哪些字符串合法",未约束"`PhaseOutput` 字段集应该 typed fold 表达"。

## Decision

**关闭 §10.11.5 amendment,落地5 件改动**:

| 改前 | 改后 |
|---|---|
| `node_graph_driver.py` 内联 `for field_name in ("decision", "observation", "reflection", "response"):` + `driver_signal.py` 内联 `port_values.get("decision")` 等四行 | **删除字面**。两处都改为 `close_out.project(port_values)` 循环,4 字段名从图驱动文件物理消失 |
| `channel.py` `PhaseOutput` 字段定义 + `channel.py` `absorb` merge 逻辑 写死4 字段名 | **从 `CLOSE_OUT_FIELDS` 派生** —— SSOT 必须包含字段定义本身,否则图驱动脱钩仍是假 SSOT |
| close-out 字段集合 = 隐式协议,藏在 3 个文件 | **SSOT 唯一定点** = `lca/cognition/close_out.py::CLOSE_OUT_FIELDS` |
| 翻译器 = driver 内的内联逻辑 | **`SubgraphCloseOut` Protocol**(`contracts/subgraph.py`) + `CognitiveCloseOut` 实现(`cognition/close_out.py`) |
| `set_outer_input` 多次调用的 `last-write-wins` 语义在 driver 内 | **不下沉**: 本次 PR 不动 `PortRegistry`, 留 ADR-0219 §5.2 独立 PR 处理 `merge` 命名 + 语义统一 |

## Boundary of new wiring

- **`contracts/`**(无 I/O、无实现): `SubgraphCloseOut` Protocol 只声明 `project(inner_outputs) -> Mapping[str, Any]`,**不列字段名**。字段名 = 实现侧私有数据。
- **`cognition/`**(SSOT): `CLOSE_OUT_FIELDS = ("decision", "observation", "reflection", "response")` + `CognitiveCloseOut` 实现 + `close_out_types()` 反查函数。改 SSOT 必须 ADR amendment,不允许外层 import 字段名。
- **`framework/subgraph/`**(纯图引擎): `NodeGraphDriver.__init__` 新增 `close_out: SubgraphCloseOut | None` 参数(默认 `CognitiveCloseOut()`,framework 兜底); `SubgraphRunner` 构造时显式注入。`run()` 内 inner-subgraph close-out 块改为 `for key, value in self._close_out.project(inner_outputs).items(): port_context.set_outer_input({key: value})`。
- **`harness/graph/execute/v2/`**(未动): `PortRegistry.set_outer_input` 已提供 last-write-wins via `dict.update`; `PortRegistry.merge_output` 是 setdefault(outer input wins)。两条语义不同,合并语义统一留 ADR-0219 §5.2 独立 PR。

## Alternatives considered

- **A. 元组留在 driver 但改成模块常量 `CLOSE_OUT_FIELDS_IN_DRIVER`**。SSOT 假象,`subgraph/` 仍认字段名,根因未动,违反 §2.1 单向层。
- **B. 只迁字段名不动 `PortRegistry.merge`**。`set_outer_input` 多次调用的 last-write-wins 是图驱动关心的策略,违反 §1.5 §6「副作用集中在 seam」。留债;留 ADR-0219 §5.2 独立 PR。
- **C. 加新独立 ADR 编号**。平行机制,AGENTS.md §4 红灯。close-out 字段名与 §10.11 同 seam 区域(均在 `node_graph_driver.py` + `channel.py`),合并回收是 ADR 自己「4 件 follow-up 一次性合拢」原则的延伸。
- **D. 把诊断 plugin (`blueprint_trajectory_differ/plugin.py:59`) 同根形态一起改**。不同根: 字段集合第 4 项为 `degradation` 而非 `response`, 触发条件有 phase 守卫, 属 observation 面合法职责。强行合一会污染诊断 plugin 的语义。记 backlog, 下次 audit 单开 Note。

## Equivalence proof

- **pytest**: `tests/integration/think/ + tests/contracts/test_subgraph_reference_contract.py + tests/unit/framework/subgraph/` 56 passed (49 baseline + 7 new close-out seam tests)。
- **e2e**: `./scripts/lca-ops runs create --user-text "用 bash 工具列出 /tmp 目录"` 跑 baseline + after: plan_ref `sha256:914b48069f3c8fa7` 一致, broken_hop `H6` 一致, error `未注册工具: bash` 一致, spine events 32 一致, duration ~3.5s 一致。
- **N7 grep**: `grep -rnE '("decision"|"observation"|"reflection"|"response")' lca/framework/subgraph/` = 0 命中。

## Delete-when(本 note 落地后)

- `grep -nE '("decision"|"observation"|"reflection"|"response")' lca/framework/subgraph/` = 0 ✅
- `lca/cognition/close_out.py::CLOSE_OUT_FIELDS` = SSOT 唯一定点 ✅
- `lca/contracts/subgraph.py::SubgraphCloseOut` Protocol 存在,只声明 `.project()` ✅
- `tests/unit/framework/subgraph/test_node_graph_driver_close_out.py`: stub `SubgraphCloseOut` 注入,断言元组字面消失 + 4 字段顺序由 stub 决定 ✅
- `tests/unit/framework/subgraph/test_phase_output_outcome_kind_field.py` + `test_inner_sub_spec_ref_branch.py` + `test_think_subgraph_inner_failure_surfaces.py` 全过 ✅
- `pytest tests/unit/framework/subgraph/ tests/integration/think/ -v` 全过 ✅
- `./scripts/lca-ops lint-imports` 与 `./scripts/lca-ops check-package-contracts` 不引入新违例(`subgraph/` 不得 import `cognition/`) ✅
- `./scripts/lca-ops runs create --user-text "ping" --wait --json` 跑通六语义 `perceive → think → act → reflect → remember → stop`,inner subgraph close-out 字段仍正确流入 outer port_context(行为等价) ✅
- ADR-0219 §11 总览表中新增的 6 条 delete-when 全过(PortRegistry.merge 单测留 ADR §5.2 独立 PR)