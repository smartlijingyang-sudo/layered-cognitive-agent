# ADR-0079: CI Four-Layer Test Discipline

## 状态

**Proposed — 2026-08-24**

Refines: [ADR-0062](0062-plugin-runtime-cleanup.md)、[ADR-0075](0075-declarative-phase-graph-and-minimal-trusted-kernel.md)、[ADR-0076](0076-six-plane-capability-layout-and-substitution-test.md)。

## 背景

当前仓库测试体系存在两类互相矛盾的契约：

- 旧路径测试仍在要求 `CognitiveRuntime._loop` 或 `self.stop_rule.decide`，验证已删除的实现
- 新路径测试验证 `CompiledRunPlan`、`GenericPlanInterpreter`、`PhaseGraph`
- 部分测试只验证静态 manifest 元数据，与生产路径无关
- 118 个插件，`plugin shape` 覆盖率仅 87.0%

「通过测试」已不能反映架构收敛度。`scripts/check_protocol_impl.py`、`check_plugin_typing.py` 等门禁只验证结构正确性，不验证运行路径正确性。

## 决策

### 一、CI 测试分四层

每个测试文件必须在 `pytest.ini` 或文件级 docstring 标注层级：

| 层 | 范围 | 失败后果 | 允许的 fixture |
|---|---|---|---|
| `contract` | typed protocol、enum、dataclass、manifest schema | 阻断合并 | 无 |
| `compile` | profile resolve / boot / plan compile / substitution gate | 阻断合并 | test fixture profile |
| `runtime_e2e` | 端到端 turn 执行、HIL 状态机、resume、cancel、recovery | 阻断合并 | 生产 profile |
| `compatibility` | 旧 facade / 迁移期 adapter / 已 deprecated 接口 | 仅记录，不阻断 | legacy profile |

CI 按层分别跑：

```yaml
- name: contract
  run: pytest -m contract
- name: compile
  run: pytest -m compile
- name: runtime_e2e
  run: pytest -m runtime_e2e
- name: compatibility
  run: pytest -m compatibility || echo "compatibility layer may have legacy failures"
  continue-on-error: true
```

`compatibility` 层只测「legacy adapter 不被生产路径引用」和「迁移 plan 已记录」，不要求旧代码本身全绿。

### 二、production gate 全绿才能合并

合并前必须全绿：

- `contract` + `compile` + `runtime_e2e` 三层 100% 通过
- `compatibility` 层失败仅允许在明确标记的迁移窗口期内，PR description 必须引用迁移 ADR
- 任意一层测试只验证「生产路径」或「迁移路径」，必须在文件 docstring 注明；未注明视为无效测试

### 三、过期测试清理

- 旧 `_loop`、`stop_rule.decide`、已删除 `cognitive-runtime-loop` 文件相关测试必须移除或移入 `compatibility` 层
- 每次移除前必须在对应 ADR 留 `Superseded by` 标记，禁止删除记录决策历史的测试
- 三个月内未在任何层运行的测试视为 dead，CI 报告但不阻断；超过六个月需删除或迁移

### 五、新增测试的最低标准

新增 `runtime_e2e` 层测试必须：

- 使用生产 profile（`web-standard.yaml`），不创建临时 profile
- 验证 journal 中至少一个对应 fact 被写入
- 验证 reducer 把 fact 折叠为正确状态字段
- 验证 result 从 TerminalOutcome 派生（见 ADR-0077）

新增 `compile` 层测试必须：

- 验证 `CompiledRunPlan` 的 `plan_hash` 稳定
- 验证 binding 完整性检查（缺失 binding 抛 `MissingBindingError`）
- 验证 substitution gate（替换某 plugin 不需修改相邻 seam）

新增 `contract` 层测试不得：

- 创建 Cordis Context
- 调用 boot / compile
- 读取 `.env`

## 后果

| 维度 | 正面 | 代价 |
|---|---|---|
| 门禁可读 | CI 输出按层分组 | 现有测试需重新标注层级 |
| 迁移透明 | compatibility 层允许失败 | 需维护迁移窗口期清单 |
| 死亡测试清理 | 三个月 / 六个月规则 | 部分历史测试需要删除 |
| 新测试质量 | 必须验证生产路径 | 新测试编写成本略升 |

**验证约束：**

- `tests/ci/test_layer_marker_required.py`：每个测试文件含 `@pytest.mark.<layer>` 或 docstring
- `tests/ci/test_production_gates_block_merge.py`：contract / compile / runtime_e2e 失败阻断合并
- `tests/ci/test_compatibility_window.py`：compatibility 失败必须有对应 ADR 引用
- `tools/ci/check_test_layer_discipline.py`：扫描 dead test（无任何 marker 且 docstring 未标注）

## 替代方案

| 方案 | 否决原因 |
|---|---|
| 保留单一 pytest 全量跑 | 无法区分「生产路径失败」与「迁移期失败」 |
| 全部移入 compatibility | 失去 production gate 意义 |
| 删除所有旧测试 | 删除 ADR 决策历史；违反 ADR lifecycle |
| 用覆盖率代替门禁 | 覆盖率可被无意义测试堆高 |