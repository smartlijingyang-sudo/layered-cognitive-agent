# 2026-08-30 — LCA 一次性整改执行计划（4 PR 同步推进）

> **Status**: Draft — pending user review
> **Date**: 2026-08-30
> **Author**: coding-agent (architectural audit triggered by `agent.py` BudgetAware/TeamUnit 混居)
> **关联文档**:
> - `2026-08-30-lca-modularization-design.md`（三阶段基础设施）
> - `docs/specs/package-organization-discipline.md`（8/10/15 规则来源）
> - `docs/specs/naming-conventions.md`（命名规范）

---

## 0. 一句话

把 `agent.py` 这种"4 概念混居"作为**症状标本**，一次性应用"4 元素声明 + 文件 = 1 概念"规则到**所有同类问题**（28 个超限目录 + 47 个 `__all__` 错位 + 218 个 Plugin 缺 `logic_address`），分 4 个独立 PR 同步推进，**不靠 CI 慢慢磨**。

---

## 1. 根因（一个，不是五个）

不是"5 层机制失灵"，是**同一个根因**：

> **没有"概念边界"的强制闸口**。CI 是辅助手段；主战场是把存量一次性按规则整改。

这一个根因产生 4 类症状：

| 症状 | 规模 | 修复路径 |
|---|---|---|
| `agent.py` 4 概念混居 | 1 文件（PR-1 子集） | PR-1 |
| `lca/contracts/protocols/` 53 文件平铺 | 53 文件 | PR-1 |
| `contracts/harness/` + `journal/` 大平铺 | 60 文件 | PR-2 |
| 28 个超限目录 | 28 包 | PR-3 |
| 89% Plugin 缺 `logic_address` | 218 个 plugin | PR-4 |
| L1 README 占位符 | 30+ README | PR-3 顺带 |

---

## 2. 统一规则（4 元素声明 + 文件 = 1 概念）

### 2.1 Plugin 必须声明的 4 元素事实单元

```python
@plugin(
    # ① Identity — 我是谁
    id="...",
    layer="L1",
    kind=PluginKind.PRIMITIVE,
    functional_group="...",
    # ② Capability — 我会什么
    implements=[Critic],
    provides=["critic.simple"],
    requires=[],
    # ③ Interaction — 我和谁交互
    logic_address=LogicAddress(
        functional_group=...,
        control_slot=...,
        scope=Scope.TURN,
        authority=("...",),
        evidence=("...",),
        revision="v1",
    ),
    relations=(PluginRelation(...),),
    ownership=OwnershipDeclaration(reads=("..",), emits=("..",), state_mutation="reducer-only"),
    # ④ Verification — 我怎么被验证
    test_suite="...",
    properties=("...",),
    fixtures=("...",),
)
```

**当前覆盖率**：身份 + 能力 ≈ 100%；交互 ≈ 11%；验证 ≈ 80%。**目标 = 100%**。

### 2.2 文件/目录规则

| 规则 | 来源 | 当前违规 |
|---|---|---|
| **P1** 一个 `.py` = 一个稳定概念 | AGENTS.md §5 | `agent.py` 等 4 概念文件 |
| **P2** 一个目录 ≤ 8 文件（> 10 必须拆） | `package-organization-discipline.md` §3 | 28 个包违规 |
| **P3** 文件名 = 概念名词，无 `helper/util/common` | `naming-conventions.md` | 暂未量化 |
| **P4** 子包命名映射 v3 九群 | `package-organization-discipline.md` §5 | `dsh/` `plane/` 等 |
| **P5** L1 README §9 = `__all__`（机器 diff） | `modularization-design.md` §4.5 | 47 个错位 |

---

## 3. 4 PR 拆分（按依赖排序、独立可合并）

```
PR-1: contracts/protocols/ 53→10 子包 + agent.py 拆 4 文件 + BudgetAware 废弃
       ↓ 样板
PR-2: contracts/harness/ 37→11 子包 + observability/journal/ 23→8 子包
       ↓
PR-3: 28 个超限目录按 8/10/15 整改 + L1 README 占位符清零
       ↓
PR-4: 245 Plugin 元数据 100% 补全（codegen + 人工审校）
```

每 PR 独立可 review / revert / 跑全量测试。

### 3.1 PR-1: `contracts/protocols/` 重构（最小变更 + 样板）

**目标**：53 文件平铺 → 10 个 v3 概念包子包；同时把 `agent.py` 拆 4 文件。

**新结构**：
```
lca/contracts/protocols/
├── __init__.py                  # 显式 __all__；无 globals()
├── README.md                    # 真正填写的 9 字段契约
├── state/                       # State/Plan/Reducer
│   ├── __init__.py
│   ├── state.py
│   ├── plan.py
│   ├── reducer.py
│   ├── scope_plan.py
│   └── delta_handler.py
├── perceive/                    # Perceive / Sensor / CapabilityPlan
│   ├── __init__.py
│   ├── capabilities.py
│   └── capability_plan.py
├── think/                       # Brain / Reasoner / Reflect
│   ├── __init__.py
│   ├── cognition.py
│   ├── cognitive_pipeline.py
│   └── learning.py
├── gate/                        # DecisionGate / BudgetPolicy / ControlVerdict
│   ├── __init__.py
│   ├── control_verdict.py
│   ├── decision_classifier.py
│   ├── gate_chain_composer.py
│   ├── loop_guard.py
│   ├── budget_policy.py         ← 从 agent.py 迁出 + 数据签名重写
│   └── lead_budget_policy.py
├── act/                         # Body / Effect / Tool
│   ├── __init__.py
│   ├── action.py
│   ├── action_handler.py
│   ├── command_envelope.py
│   ├── effect_handler.py
│   ├── embodiment.py
│   ├── tool_batch_execution.py
│   └── tool_pipeline.py
├── memory/
│   ├── __init__.py
│   ├── memory.py
│   └── operational_skills.py
├── collaboration/               # Team / Orchestration / Agent
│   ├── __init__.py
│   ├── agent.py                 ← 瘦到只剩 AgentUnit
│   ├── team_unit.py             ← 从 agent.py 迁出
│   ├── orchestration.py
│   ├── team_seam.py
│   ├── casting.py
│   └── graph_node_executor.py
├── journal/                     # Journal / Idempotency / Spec
│   ├── __init__.py
│   ├── artifact_closure.py
│   ├── idempotency.py
│   ├── journal.py
│   ├── observability.py
│   ├── phase_observation.py
│   └── spec.py
├── session/                     # Session / Turn / Resume
│   ├── __init__.py
│   ├── run_mode.py
│   ├── session_command_ledger.py
│   ├── session_persistence.py
│   ├── session_turn.py
│   └── resume_input.py
├── declarative/                 # 8 个 declarative_*.py 集中
│   ├── __init__.py
│   ├── declarative_capability.py
│   ├── declarative_common.py
│   ├── declarative_execution.py
│   ├── declarative_fault_tolerance.py
│   ├── declarative_graph.py
│   ├── declarative_phase_graph.py
│   └── declarative_plugin.py
└── composition/                 # LogicAddress / TypedRelation
    ├── __init__.py
    ├── logic_address.py
    └── relation.py
```

**关键改动**（`agent.py` 拆分）：

```python
# lca/contracts/protocols/collaboration/agent.py（瘦身后）
"""L3 Agent entry — single-agent run / resume / cancel only."""
from lca.contracts.models.core.message import AgentMessage
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import StateSnapshot
from lca.contracts.models.team.role_team import RoleProfile
from lca.contracts.models.team.run_context import RunContext


@runtime_checkable
class AgentUnit(Protocol):
    role_profile: RoleProfile
    async def run(self, task: str | AgentMessage, ctx: RunContext | None = None) -> Result: ...
    async def resume(self, snapshot: StateSnapshot, input: str | AgentMessage | None = None) -> Result: ...
    async def cancel(self) -> None: ...
```

```python
# lca/contracts/protocols/collaboration/team_unit.py（新文件）
"""L3 Team entry — end-to-end team objective run."""
from lca.contracts.models.core.message import AgentMessage
from lca.contracts.models.core.result import Result


@runtime_checkable
class TeamUnit(Protocol):
    async def run(self, objective: str | AgentMessage) -> Result: ...
```

```python
# lca/contracts/protocols/gate/budget_policy.py（新文件）
"""Budget policy seam — operates on budget data, not on agent objects.
BudgetAware marker was removed (2026-08-30 cleanup) because:
  1. Only 1 caller (LeadBudgetPolicy)
  2. Marker interfaces are an OOP anti-pattern that leak coupling
  3. Operating on data is more declarative and testable
"""
from lca.contracts.models.core.budget import BudgetLimits


@runtime_checkable
class BudgetPolicy(Protocol):
    def resolve(
        self,
        *,
        max_steps: int,
        max_wall_clock_seconds: int | None,
        role: str,
    ) -> BudgetLimits: ...
```

**级联改动**：
- `lca/application/policies.py`: `LeadBudgetPolicy.resolve(self, agent: BudgetAware)` → `resolve(self, *, max_steps, max_wall_clock_seconds, role)`
- `lca/plugins/composer/composition/agent_assembly.py:129`: `promote_lead` 调用改 `policy.resolve(max_steps=lead.max_steps, max_wall_clock_seconds=lead.max_wall_clock_seconds, role=lead.role_profile.role)`
- `lca/contracts/protocols/__init__.py`: 移除 `BudgetAware`，更新 `BudgetPolicy`/`TeamUnit` 来源路径
- `tests/characterization/test_budget_policy.py`: 重写测试用数据参数
- `tests/test_protocol_compliance.py`: 同步

**影响面**：~80 个 import 调整（自动 codegen 可生成 95%）；测试 ~10 个；文档 3 个。

**验收**：
- `uv run ruff check --fix . && uv run ruff format .` 全绿
- `uv run lint-imports` 全绿
- `uv run mypy lca` 全绿（已 `contracts/protocols/**` 排除，需保持）
- `uv run pytest tests/characterization/test_budget_policy.py tests/test_protocol_compliance.py -q` 全绿
- `uv run python scripts/check_package_size.py` 显示 `protocols/collaboration` 仍 ≤ 8
- 新 `gate/budget_policy.py` 在 L1 §9 + `__all__` 一致

**工时估算**：2-3 天。

### 3.2 PR-2: `contracts/harness/` + `journal/` 拆分

**目标**：把最大的两个平铺目录按 v3 九群拆分。

```
contracts/harness/ 37 → 11 子包：
  harness/{state,act,collaboration,journal,composition,declarative,evidence,
           plugin,session,subagent,workflow}/

infrastructure/observability/journal/ 23 → 8 子包：
  journal/{engine,otel,console,jsonl,sse,stream,enrichment,backends}/
```

**验收 + 工时**：同 PR-1；预计 3-4 天。

### 3.3 PR-3: 28 个超限目录整改 + L1 README 占位符清零

**目标**：把 28 个 `> 8 文件`目录按概念群拆，同时把所有 `{{inputs}} {{outputs}} {{failure_semantics}}` 占位符填实。

**优先级**（按 ROI）：
1. `cognition/brain/` 15 → 拆（Brain/Reasoner/Critic/Synthesizer 是不同概念）
2. `cognition/body/` 15 → 拆（tool 相关一坨）
3. `infrastructure/observability/` 27 → 拆（含 `coding_agent_tools/` 9 文件迁出）
4. `contracts/models/core/` 25 → 拆
5. `runtime/` 15 → 拆
6. 其他 23 个

**L1 README 占位符扫描**：`lca/` 下约 30 个包使用脚手架；本 PR 同步把 `{{inputs}}` 等替换为真实描述。

**验收 + 工时**：预计 5-7 天（最大 PR）。

### 3.4 PR-4: 245 Plugin 元数据 100% 补全

**目标**：245 - 27 = 218 个 plugin 补 `logic_address` + `relations` + `ownership`。

**方法**：
1. **codegen 工具**（`scripts/codegen_plugin_metadata.py`）：AST 扫描 `@plugin(...)` 调用，按启发式生成模板
2. **人工审校**：每个生成的模板过 1 分钟 review
3. **CI 闸口**：新增 `check_plugin_metadata.py`，`logic_address` 缺失阻断

**启发式映射**：
- 路径 → functional_group: `plugins/perceive/*` → perceive group；`plugins/gates/*` → decision group
- 已声明 provides → authority hints
- 已声明 requires → relations (REPLACES / FALLBACK / DEPENDS)
- 代码 import 链 → reads / emits

**验收 + 工时**：预计 4-5 天（codegen + 人工审校）。

---

## 4. 4 PR 合并序列

```
PR-1 (周一提交, 周三合) ─┬─→ PR-2 (周三提交, 周五合)
                       ├─→ PR-3 (周四启动, 跨周)
                       └─→ PR-4 (周五启动, 跨周)
```

并行执行 PR-2/3/4 可压缩到 2 周；串行约 3-4 周。

---

## 5. 风险与回退

| PR | 风险 | 回退点 |
|---|---|---|
| PR-1 | 改 BudgetPolicy 签名是 breaking change | `git revert` 整 PR；改回时同步更新 `application/policies.py` 与 `promote_lead` |
| PR-1 | 53 文件重组 import 改动量大 | codegen 生成的 import 替换脚本可单独 revert |
| PR-2 | harness 子目录多，ADR-0096 linter 可能误报 | `pyproject.toml` 的 `tool.importlinter` 路径配置 |
| PR-3 | 28 个目录同时拆，PR 太大 | 拆 3 个子 PR：3a cognition/brain+body；3b observability+models；3c 其他 |
| PR-4 | codegen 误判 | `legacy_blacklist.txt` 机制 + 包级 `metadata_whitelist` |

---

## 6. 验收（4 PR 全完成）

- [ ] 28 个超限目录 ≤ 8 文件（`check_package_size.py` 0 报错）
- [ ] `lca/contracts/protocols/` 47 个 `__all__` 错位为 0（`check_package_contracts.py` 0 报错）
- [ ] 218 个 plugin `logic_address` 100% 覆盖（`check_plugin_metadata.py` 0 报错）
- [ ] L1 README 占位符为 0（`check_readme_filled.py` 0 报错）
- [ ] `BudgetAware` 类已删除（`grep -rn BudgetAware lca/` 为空）
- [ ] `TeamUnit` 不再在 `agent.py`（`grep -n TeamUnit lca/contracts/protocols/collaboration/agent.py` 为空）
- [ ] 既有 CI（`lint-imports` / `mypy lca` / `pytest` / `vulture`）全绿
- [ ] 至少 1 个 E2E 测试通过（`tests/e2e/`）

---

## 7. ADR 关联

需要新增：
- **ADR-0107**: `BudgetAware` 废弃；`BudgetPolicy` 改为数据签名
- **ADR-0108**: 4 元素 Plugin 声明作为强契约（PR-4 前置）
- **ADR-0109**: 28 个超限目录整改路线图（PR-3 前置）

需要更新：
- ADR-0074（plugin 体系）：增加 4 元素事实单元
- `docs/specs/naming-conventions.md`：增加"marker 接口禁用"条款
- `docs/specs/package-organization-discipline.md`：从 Proposed → Accepted