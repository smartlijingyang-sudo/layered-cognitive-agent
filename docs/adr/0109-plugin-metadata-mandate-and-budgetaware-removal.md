# ADR-0109: Plugin 4-Element Declaration Mandate + BudgetAware Removal

> **状态:** Accepted（PR-1 已落地；PR-4 在编）
> **日期:** 2026-08-30
> **依赖:** [ADR-0105 包组织纪律](./0105-package-organization-discipline.md)、[ADR-0106 命名宪法](./0106-naming-constitution.md)、[ADR-0108 Phase D/E](./0108-phase-de-and-e.md)

## 背景

2026-08-30 架构审查触发：审计 `lca/contracts/protocols/collaboration/agent.py`
时发现 4 个不相关概念混居（`AgentUnit`、`TeamUnit`、`BudgetAware`、`BudgetPolicy`）。
调查显示根因不是单文件问题，而是**两层机制同时缺失**：

### 缺失 1：Plugin 元数据不强制
194 个 plugin 中 **0 个**声明完整的 4 元素事实单元：
- Identity（id / layer / kind）— 100% 已有
- Capability（provides / requires / implements）— 100% 已有
- Interaction（logic_address / relations / ownership）— 11% 声明
- Verification（test_suite / properties）— ~80% 声明

读 89% 的 plugin 不知道"它和谁交互、产出什么事件、能做什么副作用"。
这是 `deepseek-harness` 类大包的核心病——plugin 内部塞太多逻辑且不自描述。

### 缺失 2：Marker 接口作为"我知道什么"谓词
`BudgetAware` 是 OOP 老旧约定的 marker 接口（"Aware" 后缀仅描述"知道什么"）。
仅 1 处生产调用（`LeadBudgetPolicy`），且调用方完全可以传递原始数据。
Marker 接口泄漏 agent 对象图耦合，是反模式。

## 决定

### D1. Plugin 必须声明 4 元素事实单元

每个 `@plugin(...)` 装饰器调用必须包含：

| 元素 | 必填字段 | 现状 → 目标 |
|---|---|---|
| **Identity** | `id`, `layer`, `kind` | 100% → 100% |
| **Capability** | `implements`, `provides`, `requires` | 100% → 100% |
| **Interaction** | `logic_address` (含 functional_group, control_slot, scope, authority, evidence, revision), `relations`, `ownership` | 11% → 100% |
| **Verification** | `test_suite` (required), `fixtures` | ~80% → 100% |

CI 闸口：`scripts/check_plugin_metadata.py`（新增；PR-1 已加入 `pyproject.toml [tool.lca.lint-checks]`）。
- 缺 `logic_address` 或 `ownership` → 阻断合并
- 缺 `relations` 或 `test_suite` → warning（季度清理升级）

### D2. 废弃 Marker 接口；策略接缝改数据签名

**`BudgetAware` 删除**，无替代（消费者直接传数据）。

**`BudgetPolicy.resolve` 签名变更**：
```python
# 旧
def resolve(self, agent: BudgetAware) -> BudgetLimits: ...

# 新
def resolve(
    self,
    *,
    max_steps: int,
    max_wall_clock_seconds: int | None,
    role: str,
) -> BudgetLimits: ...
```

调用方解构 agent 字段后转发。已落地（PR-1 commit `1d60c5e4`）。

### D3. "Aware / Can / Has / With" 前缀 marker 接口禁用

新增规范条款（合并到 `docs/specs/naming-conventions.md`）：
- 任何以 `Aware` / `Can` / `Has` / `With` 开头、仅描述谓词的 Protocol 必须审查
- 默认改为：操作数据；或合并；或重命名为 `XSubject` / `XTarget`

## 影响面盘点

- **代码层**：
  - `lca/contracts/protocols/collaboration/agent.py`：63 → 33 行（仅 AgentUnit）
  - `lca/contracts/protocols/collaboration/team_unit.py`：新建（TeamUnit）
  - `lca/contracts/protocols/gate/budget_policy.py`：新建（BudgetPolicy 数据签名）
  - `lca/contracts/protocols/gate/lead_budget_policy.py`：import 路径更新
  - `lca/contracts/protocols/__init__.py`：BudgetAware 从 barrel 删除
  - `lca/application/policies.py`：LeadBudgetPolicy.resolve 数据签名
  - `lca/plugins/composer/composition/agent_assembly.py`：promote_lead 解构 agent 转发
- **测试层**：`tests/characterization/test_budget_policy.py` 重写（MagicMock + Protocol → keyword-only 数据）
- **CI 闸口层**：`pyproject.toml [tool.lca.lint-checks]` 补 9 个缺失 check（Phase D），新增 `check_plugin_metadata.py`
- **破坏性变更**：BudgetAware 删除；BudgetPolicy.resolve 签名变更；external consumer 需解构 agent 后转发

## 关联

- 配套设计文档：`docs/superpowers/specs/2026-08-30-comprehensive-cleanup-execution.md` §2.1（4 元素声明）、§3.1（PR-1 拆分）
- 影响面盘点：`docs/superpowers/specs/2026-08-30-impact-inventory.md` §1（agent.py 拆分）、§4（Plugin 元数据）
- 实施 PR：
  - `refactor(contracts)!: split agent.py + remove BudgetAware`（commit `1d60c5e4`，已合并）
  - PR-4（进行中）：194 plugin 元数据 100% 补全

## 回退策略

PR-1 的 BudgetAware 删除 + BudgetPolicy 签名变更是 **breaking change**。
如需回退：
1. `git revert 1d60c5e4` 完整 revert（git mv 与 import 同步改，不可单独 revert）
2. 检查 `promote_lead` 调用点是否需要同步 revert
3. 重新评估"marker 接口 vs 数据签名"决策

后续若发现需要 marker 接口模式，必须新增 ADR 解释为何 D2 不适用。