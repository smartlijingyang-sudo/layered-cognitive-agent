# 2026-08-30 — LCA 整改影响面清单

> **Status**: Auto-generated, ready for review
> **Date**: 2026-08-30
> **Source**: `scripts/codegen_plugin_metadata.py --scan --json` + `scripts/check_package_size.py` + `scripts/check_package_contracts.py`
> **关联**: `2026-08-30-comprehensive-cleanup-execution.md`

---

## 0. 总量

**`BudgetAware` 引用清单**（全仓库 `*.py`，排除 vendor）：

1. `lca/contracts/protocols/__init__.py`（barrel re-export）
2. `lca/contracts/protocols/collaboration/agent.py`（定义）
3. `lca/application/policies.py`（唯一生产调用方）
4. `tests/characterization/test_budget_policy.py`（测试）

---

| 指标 | 当前 | 目标 | 差量 |
|---|---|---|---|
| Plugin 总数 | 194 | 194 | — |
| Plugin 4 元素齐全（logic_address + relations + ownership + test_suite） | **0** | 194 | **+194** |
| Plugin critical（缺 ≥ 3 元素） | 167 | 0 | **−167** |
| Plugin warning（缺 1–2 元素） | 27 | 0 | **−27** |
| 超限目录（> 8 文件） | **28** | 0 | **−28** |
| `__all__` vs L1 §9 错位 | **271** 行（81 包） | 0 | **−271** |
| README 含 `{{inputs}}` 占位符 | 0 | 0 | ✓ |
| README 含"脚手架生成"文本 | **3** | 0 | **−3** |
| `BudgetAware` 引用点 | 4 文件（含 tests/）| 0 | **−4** |
| `TeamUnit` 在 agent.py 中 | 1 | 0 | **−1** |

---

## 1. PR-1 影响面：contracts/protocols/ 重构

### 1.1 `agent.py` 拆分

**当前文件**：`lca/contracts/protocols/collaboration/agent.py`（63 行 / 4 概念）

**目标拆分**：

| 新文件 | 行数估计 | 包含 |
|---|---|---|
| `collaboration/agent.py` | ~22 | 仅 `AgentUnit` |
| `collaboration/team_unit.py`（新） | ~10 | `TeamUnit` |
| `gate/budget_policy.py`（新） | ~17 | `BudgetPolicy`（数据签名） |
| `gate/__init__.py` | ~5 | re-export |

### 1.2 BudgetAware 废弃影响

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `lca/contracts/protocols/collaboration/agent.py` | 删除 BudgetAware + BudgetPolicy 类 | 第 35-57 行删除 |
| `lca/contracts/protocols/__init__.py` | 移除 BudgetAware 导入 + `__all__` | 1 行删除 + 1 行 `__all__` 删除 |
| `lca/contracts/protocols/gate/budget_policy.py`（新） | 新建文件 | 数据签名 `resolve(*, max_steps, max_wall_clock_seconds, role)` |
| `lca/application/policies.py` | `LeadBudgetPolicy.resolve(self, agent: BudgetAware)` → `resolve(self, *, max_steps, max_wall_clock_seconds, role)` | 函数体改写 |
| `lca/plugins/composer/composition/agent_assembly.py:129` | `promote_lead` 调用改 `policy.resolve(max_steps=lead.max_steps, ...)` | 1 处调用改 |
| `tests/characterization/test_budget_policy.py` | 重写测试用数据参数 | 全文重写（~75 行） |
| `tests/test_protocol_compliance.py` | 同步（如果含 BudgetAware） | 待确认 |

### 1.3 `__init__.py` 271 个 `__all__` 错位（PR-1 子任务）

按 `check_package_contracts.py` 输出，错位集中在：

| 包 | 错位行数（估） | 说明 |
|---|---|---|
| `lca.contracts.protocols` | ~50 | 47 个之前报告的 |
| `lca.infrastructure.observability` | ~18 | 18+ symbols |
| 其他 79 包 | ~200 | 散落各处 |

**修复路径**：codegen 把 `__all__` 与 L1 §9 对齐；或反过来——把 L1 §9 用 `__all__` 覆盖。

---

## 2. PR-2 影响面：contracts/harness + observability/journal 拆分

### 2.1 `lca/contracts/harness/`（37 → 11 子包）

按 v3 九群切：

```
harness/
├── state/{...}            # checkpoint/resolve/loader
├── act/{...}              # 行动装配
├── collaboration/{...}    # 协作相关
├── journal/{...}          # 日志装配
├── composition/{...}      # 组合器
├── declarative/{...}      # 声明式
├── evidence/{...}         # 证据
├── plugin/{...}           # 插件相关
├── session/{...}          # 会话
├── subagent/{...}         # 子代理
└── workflow/{...}         # 工作流
```

**预估改动**：~120 个 import 调整（codegen 可生成 90%）；1 个 ADR（接受新结构）。

### 2.2 `lca/infrastructure/observability/journal/`（23 → 8 子包）

```
journal/
├── engine/{...}            # RunStore, reducer, serialization
├── otel/{...}              # OTel 相关
├── console/{...}           # 控制台渲染
├── jsonl/{...}             # JSONL 持久化
├── sse/{...}               # SSE 流
├── stream/{...}            # 流处理
├── enrichment/{...}        # 富化
└── backends/{...}          # 后端（filesystem/memory）
```

**预估改动**：~80 个 import 调整；新增 1 个 L1 README。

---

## 3. PR-3 影响面：28 个超限目录整改

### 3.1 28 个违规包（按文件数降序）

| 包 | 文件数 | 概念群归属 | 整改策略 |
|---|---|---|---|
| `infrastructure/observability/` | 27 | journal | PR-2 已涵盖（含 `coding_agent_tools/` 9 文件迁出到 `plugins/tools/diagnostics/`） |
| `contracts/models/core/` | 25 | state/data | 拆 4 子包：`state/`、`lifecycle/`、`memory/`、`message/` |
| `contracts/observability/` | 19 | journal | 拆 `journal/`、`evidence/`、`cost/`、`diagnostic/`、`event/` |
| `infrastructure/comparison/dsh_driver/` | 18 | comparison | 拆 `driver/`、`mapping/`、`bridge/` |
| `infrastructure/sandbox/` | 18 | sandbox | 拆 `runtime/`、`policy/`、`mount/` |
| `plugins/phase_graph/` | 18 | plan | 拆 `node/`、`edge/`、`executor/`、`topology/` |
| `plugins/seams/observability/` | 16 | compose | 拆 `journal/`、`otel/`、`tracer/` |
| `harness/profile/` | 16 | compose | 拆 `resolve/`、`boot/`、`evolution/` |
| `cognition/body/` | 15 | act | 拆 `tool/`、`executor/`、`pipeline/` |
| `cognition/brain/` | 15 | think | 拆 `prompt/`、`critic/`、`synthesizer/` |
| `runtime/` | 15 | runtime | 拆 `loop/`、`lifecycle/`、`checkpoint/` |
| `infrastructure/computer/` | 13 | computer | 拆 `driver/`、`bridge/`、`policy/` |
| `infrastructure/skills/` | 13 | skill | 拆 `registry/`、`loader/`、`installer/` |
| `plugins/providers/observability/` | 13 | compose | 拆 `journal/`、`tracer/`、`otel/` |
| `plugins/control_contributions/` | 12 | decision | 改名为 `cognitive_steps/`（已在 package-organization-discipline.md §5.1 列入） |
| `infrastructure/tools/lca_computer/apis/` | 13 | tool | 拆 `lifecycle/`、`execution/` |
| `contracts/atoms/` | 11 | atoms | 拆 `ids/`、`enums/`、`scopes/` |
| `contracts/models/team/` | 11 | team | 拆 `role/`、`spec/`、`coordination/` |
| `infrastructure/capability/` | 12 | capability | 拆 `registry/`、`grant/`、`scope/` |
| `infrastructure/cli/commands/` | 12 | cli | 拆 `run/`、`profile/`、`diagnose/` |
| `application/` | 12 | compose | 拆 `api/`、`spawn/`、`builder/` |
| `harness/` | 12 | harness | 拆 `profile/`、`declarative/` |
| `plugins/composer/runtime/` | 9 | compose | 拆 `binding/`、`assembly/` |
| `harness/agent/` | 10 | harness | 拆 `lifecycle/`、`command/` |
| `infrastructure/cli/` | 10 | cli | 拆 `commands/`、`config/` |
| `harness/diagnostics/` | 9 | diagnostics | 拆 `tree/`、`scope/`、`run/` |
| `infrastructure/` | 9 | infrastructure | 顶层需拆 |

### 3.2 L1 README 占位符清零

**3 个** README 含"脚手架生成"文本：

| 文件 | 路径 |
|---|---|
| `lca/plugins/think/README.md` | 待清空 |
| `lca/plugins/bundles/README.md` | 待清空 |
| `lca/plugins/creator/README.md` | 待清空 |

注：30+ 包 README 是显式 9 字段契约，但部分章节仍是空泛表述（"待包负责人补充"），需补全。

---

## 4. PR-4 影响面：245 Plugin 元数据补齐

### 4.1 分布（按层）

```
L0: 67 plugins     （基础设施提供者）
L1: 52 plugins     （核心实现）
L2: 42 plugins     （运行时控制）
L3: 22 plugins     （会话/团队）
L4: 11 plugins     （组合根）
```

### 4.2 分布（按功能群，codegen 推断）

| FunctionalGroup | 数量 |
|---|---|
| G10_COMPOSE（组合/提供者） | 76 |
| G6_DECISION（控制/门） | 21 |
| G5_REMEMBER（记忆） | 21 |
| G3_THINK（思考） | 17 |
| G9_COLLABORATE（协作） | 16 |
| G7_PLAN（计划） | 15 |
| G8_ACT（行动） | 13 |
| G2_PERCEIVE（感知） | 13 |
| G4_REFLECT（反思） | 2 |

**注**：这是 codegen 按路径启发式推断，**不是真理**。人工审校需要：
- 确认 functional_group 是否准确
- 调整 authority 列表（codegen 可能漏判凭证）
- 调整 evidence 列表（应反映该 plugin 实际产出的事件）

### 4.3 codegen 工具产物

`scripts/codegen_plugin_metadata.py` 已实现：
- `--scan`：报告每个 plugin 缺口（167 critical + 27 warning）
- `--generate`：输出每个 plugin 的 template 代码（可复制粘贴）
- `--json`：机器可读输出（已保存到 `/tmp/plugin_metadata_scan.json`，5589 行）

**完整模板示例**（`safe_executor.simple`）：

```python
ownership=OwnershipDeclaration(
    reads=(),
    emits=("plugin.served",),
    state_mutation="forbidden",
),
relations=(),
```

**带 logic_address 的模板示例**（`lca-brain-modular`）：

```python
logic_address=LogicAddress(
    functional_group=FunctionalGroup.G3_THINK,
    control_slot=ControlSlot.LCA-BRAIN-MODULAR,
    scope=Scope.TURN,
    authority=('plugin.serve',),
    evidence=('lca-brain-modular.checked', 'lca-brain-modular.served'),
    revision="v1",
),
ownership=OwnershipDeclaration(
    reads=(),
    emits=("plugin.served",),
    state_mutation="forbidden",
),
relations=(),
```

---

## 5. 跨 PR 共性改动

### 5.1 必须新增的 CI 闸口

```python
# scripts/check_plugin_metadata.py（PR-4 前置）
def check_logic_address_complete(file): ...
def check_ownership_declaration(file): ...
def check_relations_when_required(file): ...
def main() -> int:  # exit 1 if any plugin missing metadata
```

### 5.2 必须新增/更新的 ADR

| ADR | 内容 | 时机 |
|---|---|---|
| ADR-0107 | BudgetAware 废弃 + BudgetPolicy 数据签名 | PR-1 前 |
| ADR-0108 | 4 元素 Plugin 声明为强契约 | PR-4 前 |
| ADR-0109 | 28 个超限目录整改路线图 | PR-3 前 |
| ADR-0110 | package-organization-discipline.md 升 Accepted | Phase 0 |

### 5.3 必须更新的文档

| 文档 | 改动 |
|---|---|
| `AGENTS.md §3` | 增加"4 元素 Plugin 声明"条款 |
| `AGENTS.md §5` | 增加"marker 接口禁用"条款 |
| `docs/specs/naming-conventions.md` | 增加"Aware/Can/Has/With 前缀 marker 接口禁用" |
| `docs/specs/package-organization-discipline.md` | 从 Proposed → Accepted |
| `docs/adr/0074` | plugin 体系增加 4 元素事实单元 |

---

## 6. 执行优先级

```
本周 (P0):   PR-1 启动 → 周三前合
下周 (P1):   PR-2 + PR-3a 并行（harness + cognition/brain+body）
本季度 (P2): PR-3b + PR-3c（其他 23 个违规目录）
本季度末:    PR-4（codegen + 人工审校）
```

**关键约束**：每个 PR 完成后，必须等 ADR 接受 + CI 全绿 + 至少 1 个 E2E 通过，才能进下一个。

---

## 7. 验证矩阵

| 检查 | 工具 | PR-1 后 | PR-2 后 | PR-3 后 | PR-4 后 |
|---|---|---|---|---|---|
| 8/10/15 越线 | `check_package_size.py` | 27 → 27 | 27 → 25 | 25 → 0 | 0 |
| L1↔__all__ 错位 | `check_package_contracts.py` | 271 → 50 | 50 → 30 | 30 → 0 | 0 |
| Plugin metadata | `check_plugin_metadata.py`（新） | 194 → 194 | 194 | 194 | 194 → 0 |
| README 占位符 | `check_readme_filled.py` | 3 → 3 | 3 → 1 | 1 → 0 | 0 |
| import-linter | `lint-imports` | ✓ | ✓ | ✓ | ✓ |
| mypy lca | `mypy lca` | ✓ | ✓ | ✓ | ✓ |
| pytest | `pytest` | ✓ | ✓ | ✓ | ✓ |
| vulture | `vulture lca` | ✓ | ✓ | ✓ | ✓ |

---

## 8. 风险与回退

| 风险 | 缓解 | 回退点 |
|---|---|---|
| PR-1 改 BudgetPolicy 签名是 breaking | 所有调用点（仅 1 处：`promote_lead`）同步改 | git revert 整 PR |
| PR-2 harness 子目录多，import-linter 误报 | 提前在 `pyproject.toml` 配置 layers | 修正 linter 配置 |
| PR-3 28 个目录同时拆 | 拆 3 子 PR（3a cognition；3b observability+models；3c 其他） | 子 PR 独立 revert |
| PR-4 codegen 误判 | `legacy_blacklist.txt` + 包级 `metadata_whitelist` | 误判时加 whitelist |
| L1 README 写完没人 review | 责任人表（pyproject `[tool.lca.package_contracts.<pkg>].owner`） | 季度 review |

---

## 9. 数据附件

完整 codegen 输出：`/tmp/plugin_metadata_scan.json`（5589 行）
完整 `check_package_contracts.py` 输出：可重跑 `uv run python scripts/check_package_contracts.py 2>&1 | tee /tmp/contracts.log`
完整 `check_package_size.py` 输出：可重跑 `uv run python scripts/check_package_size.py 2>&1 | tee /tmp/size.log`