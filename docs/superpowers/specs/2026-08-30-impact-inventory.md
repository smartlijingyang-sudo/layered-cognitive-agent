# 2026-08-30 — LCA 整改影响面清单

> **Status**: Auto-generated, ready for review
> **Date**: 2026-08-30
> **Source**: `scripts/codegen_plugin_metadata.py --scan --json` + `scripts/check_package_size.py` + `scripts/check_package_contracts.py`
> **关联**: `2026-08-30-comprehensive-cleanup-execution.md`

---

## 0. 现状（2026-08-30 末次更新）

**`BudgetAware` 引用清单**（全仓库 `*.py`，排除 vendor）：

- 0 实际代码引用（仅 4 处 docstring/comment 提及历史）
- 类已删除；`BudgetPolicy.resolve` 改数据签名

| 指标 | 当前 | 起始 | 目标 | 差量 |
|---|---|---|---|---|
| Plugin 总数 | 194 | 194 | 194 | — |
| Plugin logic_address 已声明 | **12**（control_contributions）| 5 | 194 | **+189** |
| Plugin critical（缺 logic_address） | 160 | 167 | 0 | **−7** ✅ |
| 超限目录（> 8 文件） | 28 | 28 | 0 | **0**（待 PR-3）|
| `__all__` vs L1 §9 错位 | **0** | 271 | 0 | **−271** ✅ |
| Total FAIL（`check_package_contracts.py`） | **354** | 626 | 0 | **−272** ✅ |
| README 含"脚手架生成"文本 | 3 | 3 | 0 | **0**（待）|
| `BudgetAware` 引用点 | 0（除 docstring）| 4 | 0 | **−4** ✅ |
| `TeamUnit` 不在 agent.py | 0 | 1 | 0 | **−1** ✅ |

**已落地 PR**：
- `refactor(contracts)!: split agent.py + remove BudgetAware`（commit `1d60c5e4`）
- `feat(ci)!: add missing CI gates + ADR-0109`（commit `04ea3171`）
- `feat(plugins): add logic_address to 12 control_contributions plugins`（commit `0f887e77`）
- `docs(protocols): sync L1 §9 public API with __all__`（commit `b41c2e25`）

**剩余 backlog**：
- 160 critical plugin 缺 logic_address（PR-4 续）
- 354 L1↔L2 + L1 缺失 README 错位（批量加 §6 禁止依赖段）
- 28 个超限目录（PR-3 大重构）
- 3 个 README "脚手架生成" 文本

---

## 1. PR-1 影响面：contracts/protocols/ 重构

### 1.1 `agent.py` 拆分

**当前文件**：`lca/contracts/protocols/collaboration/agent.py`（63 行 / 4 概念）


> 下面是历史内容（保留以备 audit）。当前 PR-1 (A) 已落地：(B) 子包组织在先前已就绪。

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
| `tests/test_protocol_compliance.py` | 同步（如果含 BudgetAware） | 已确认无引用 |

### 1.3 `__init__.py` 271 个 `__all__` 错位 ✅ 已修

按 `check_package_contracts.py` 输出，错位集中在：

| 包 | 错位行数（修复前） | 状态 |
|---|---|---|
| `lca.contracts.protocols` | 165 | **0**（commit `b41c2e25`）|
| `lca.infrastructure.observability` | 97 | **0**（commit `b41c2e25`）|
| `lca.contracts.harness` | 10 | **0**（commit `b41c2e25`）|
| 其他 78 包 | ~0 | 0 |
| **合计** | **272** | **0** ✅ |

**修复路径**：用 `/tmp/sync_l1_readme.py` 同步 `__all__` → L1 §9。

---

## 2. PR-2 影响面：contracts/harness + observability/journal 拆分

### 2.1 `lca/contracts/harness/`（37 → 11 子包）**已就绪**

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

每个子包 ≤ 6 文件（实测）。

### 2.2 `lca/infrastructure/observability/journal/`（23 → 8 子包）**已就绪**

```
journal/
├── engine/{...}            # RunStore, reducer, serialization (5 files)
├── otel/{...}              # OTel 相关 (4 files)
├── console/{...}           # 控制台渲染 (4 files)
├── jsonl/{...}             # JSONL 持久化 (1 file)
├── sse/{...}               # SSE 流 (1 file)
├── stream/{...}            # 流处理 (3 files)
├── enrichment/{...}        # 富化 (1 file)
└── backends/{...}          # 后端 (2 files)
```

每个子包 ≤ 5 文件（实测）。顶层 `__init__.py` 仅 1 个文件。

---

## 3. PR-3 影响面：28 个超限目录整改（**待执行**）

### 3.1 28 个违规包（按文件数降序）

| 包 | 文件数 | 整改策略 |
|---|---|---|
| `infrastructure/observability/` | 27 | PR-2 已涵盖（含 `coding_agent_tools/` 9 文件迁出到 `plugins/tools/diagnostics/`） |
| `contracts/models/core/` | 25 | 拆 4 子包 |
| `contracts/observability/` | 19 | 拆 5 子包 |
| `infrastructure/comparison/dsh_driver/` | 18 | 拆 3 子包 |
| `infrastructure/sandbox/` | 18 | 拆 3 子包 |
| `plugins/phase_graph/` | 18 | 拆 4 子包 |
| `plugins/seams/observability/` | 16 | 拆 3 子包 |
| `harness/profile/` | 16 | 拆 3 子包 |
| `cognition/body/` | 15 | 拆 3 子包 |
| `cognition/brain/` | 15 | 拆 3 子包 |
| `runtime/` | 15 | 拆 3 子包 |
| `infrastructure/computer/` | 13 | 拆 3 子包 |
| `infrastructure/skills/` | 13 | 拆 3 子包 |
| `plugins/providers/observability/` | 13 | 拆 3 子包 |
| `plugins/control_contributions/` | 12 | 改名 `cognitive_steps/`（已在 discipline §5.1） |
| `infrastructure/tools/lca_computer/apis/` | 13 | 拆 3 子包 |
| `contracts/atoms/` | 11 | 拆 3 子包 |
| `contracts/models/team/` | 11 | 拆 3 子包 |
| `infrastructure/capability/` | 12 | 拆 3 子包 |
| `infrastructure/cli/commands/` | 12 | 拆 5 子包 |
| `application/` | 12 | 拆 3 子包 |
| `harness/` | 12 | 拆子包（plugin_api / manifest / context） |
| `plugins/composer/runtime/` | 9 | 拆 2 子包 |
| `harness/agent/` | 10 | 拆 2 子包 |
| `infrastructure/cli/` | 10 | 拆子包 |
| `harness/diagnostics/` | 9 | 拆 2 子包 |
| `infrastructure/` | 9 | 顶层需拆 |
| `cognition/` | 9 | 顶层需拆 |

**预估改动**：~200+ 文件移动 + import 调整；大量 README 重写。

### 3.2 L1 README 占位符清零

**3 个** README 含"脚手架生成"文本（待修）：

| 文件 | 路径 |
|---|---|
| `lca/plugins/think/README.md` | 待清空 |
| `lca/plugins/bundles/README.md` | 待清空 |
| `lca/plugins/creator/README.md` | 待清空 |

---

## 4. PR-4 影响面：194 Plugin 元数据补齐（**部分完成**）

### 4.1 当前分布（按层）

```
L0: 67 plugins
L1: 52 plugins
L2: 42 plugins
L3: 22 plugins
L4: 11 plugins
```

### 4.2 当前状态

- `logic_address` 已声明：**12 / 194** = **6%**（control_contributions + 5 act_*）
- critical 缺 logic_address：**160 / 194** = **82%**
- 待办：~148 个 plugin

### 4.3 codegen 工具产物

`scripts/codegen_plugin_metadata.py --generate` 已能产出 167 个 plugin 的 template。
**人工审校时间估算**：每个 plugin ~30 秒 × 148 ≈ 75 分钟。

---

## 5. 已落地新增 CI 闸口

`pyproject.toml [tool.lca.lint-checks]` 已补 9 个缺失 check + 1 个新增：

- `scripts/check_package_size.py`（8/10/15）
- `scripts/check_package_contracts.py`（L1/L2 一致性）
- `scripts/check_package_noun.py`
- `scripts/check_filename_boundaries.py`
- `scripts/check_no_utility_modules.py`
- `scripts/check_no_barrel_glob.py`
- `scripts/check_package_integrity.py`
- `scripts/check_readme_filled.py`
- **`scripts/check_plugin_metadata.py`**（新增，PR-4 闸口）

---

## 6. 跨 PR 共性改动

### 6.1 已新增 ADR

- **ADR-0109**: Plugin 4-Element 声明为强契约 + BudgetAware 废弃 + BudgetPolicy 数据签名（Accepted）

### 6.2 ADR 关联文档

| 文档 | 状态 |
|---|---|
| `docs/specs/package-organization-discipline.md` | Proposed（待升 Accepted）|
| `docs/superpowers/specs/2026-08-30-comprehensive-cleanup-execution.md` | 计划文档 |
| `docs/superpowers/specs/2026-08-30-impact-inventory.md` | 本文件 |

---

## 7. 执行优先级（**当前已完成部分**）

```
本周 (P0):   ✅ PR-1 agent.py 拆分 + BudgetAware 废弃
本周 (P0):   ✅ CI 闸口补 9 项 + ADR-0109
本周 (P0):   ✅ 12 个 control_contributions 加 logic_address
本周 (P0):   ✅ L1↔__all__ 271 错位全部同步
下周 (P1):   ⚠️ PR-4 续：剩余 160 plugin 加 logic_address
下周 (P1):   ⚠️ L1↔L2 354 错位批量修
本季度 (P2): ⚠️ PR-3 28 个超限目录整改
本季度 (P3): ⚠️ 3 个 README 占位符清零
```

**关键约束**：每个 PR 完成后，必须等 ADR 接受 + CI 全绿 + 至少 1 个 E2E 通过，才能进下一个。