# 2026-08-30 — LCA 模块化、契约化、命名规范化 三阶段重构设计

> **Status**: Draft, pending user review
> **Date**: 2026-08-30
> **Scope**: `lca/` 一级 + 二级包结构、`pyproject.toml`、`scripts/`、`docs/`、`profiles/`、`deploy/lobehub/patches/`、`tests/`
> **Out of scope**: `lobehub-ui/`（vendored LobeHub，仅消费 Projector；patches 同步）、`vendor/{cordis,cosmokit,schemastery}`（vendored，仅在升级时改）、`history/`（只读）

---

## 0. 背景

LCA 现有架构基础较强：五层单向分层（`contracts → layer0_infra → layer1_cognitive → layer2_runtime → layer3_agent` + `layer4_app` 组合根）、`import-linter` 5 条 contracts、73 个 ADR、`docs/specs/naming-conventions.md` 命名规范、约 30 个 `check_*.py` 守门脚本、`docs/specs/documentation-map.md` 文档地图、AGENTS.md coding agent 指南。

但当前状态在三个具体方面没有强约束，导致新贡献者上手成本依然偏高：

1. **包职责不外显**：开发者必须先读 AGENTS.md §3 + 多个 ADR + `docs/specs/lca-structured-cognition-guide.md` 才能判断"这个包能放什么、不能放什么"。每个包没有机器可读的契约。
2. **层名是编号不是语义**：`lca.infrastructure` / `lca.cognition` / `lca.layer2_runtime` / `lca.layer3_agent` / `lca.layer4_app` 表达顺序清晰，但表达职责模糊；新人需要"先背 L0–L4 顺序 → 再查 ADR-0001 才知道每个层做什么"。
3. **命名规范只在文档**：`docs/specs/naming-conventions.md` 已经明确禁 `Impl / Manager / Helper / Common`，但仓库仍有历史违规文件（如 `trace_tool.py` 一类的"tool" 后缀），且无 CI 强约束，新代码仍可能继续引入模糊命名。

这三点不是"再增加新层"能解决的；最有效的方向是**把已有架构约束显式化、可机器验证、覆盖老代码**。

---

## 1. 设计决策

**D1.** 重构分三个独立阶段、按依赖顺序执行：**Phase 1（包契约显式化）→ Phase 2（目录语义化）→ Phase 3（命名规范自动化）**。任一阶段失败或回退不影响其它阶段的进入判定。

**D2.** 引入 4 层契约执行栈（L1–L4）作为三阶段的共同基础设施：

- **L1 文档真相**：每个一级 + 二级包一个 `README.md`，9 字段模板
- **L2 机器契约**：`pyproject.toml` 的 `[tool.lca.package_contracts.<pkg>]` 段，镜像 L1 可验证字段
- **L3 架构边界**：扩展 `import-linter` 的 `forbidden` + `independence` 规则
- **L4 一致性闸口**：新增 `scripts/check_package_contracts.py`，扫 L1↔L2↔L3↔实际 import 四向一致性

**D3.** Phase 2 采用**一次性切换，无兼容期**：旧名 `lca.infrastructure` 等在新 PR 完成后立即消失，不留 shim。`lca.harness` / `lca.plugins` / `lca.contracts` / `gateway` 不参与重命名（避免冲击外部消费方与已有 ADR）。C1–C7 闭集纪律仍然生效：必须先有 ADR，删除与改名必须原子，CI 绿是切换的前置条件。

**D4.** 公共 API 与内部路径**严格区分**：外部可能消费的 `lca.contracts.*` 数据/协议、`lca.harness.plugin_api`、`profiles/*.yaml` schema 在三阶段中严格保留兼容；内部子包（如 `lca.cognition.brain.*`）可自由改名。判断标准：是否在 `docs/AGENTS.md` §2 仓库地图或 ADR 中被列为公共入口。

**D5.** 命名规范自动化的过渡期采用**渐进升级**：新代码立即 error，已有违规文件先 warning，季度清理升级为 error。legacy_blacklist 与 whitelist 机制共存，避免误判历史文件。

**D6.** 三阶段均**遵守闭集纪律**：所有路径变更、契约字段新增、linter 规则调整必须先有 ADR，CI 强制点（绿/不绿）在每阶段进入前明确，不允许"差不多就行"。

---

## 2. 不变量（Invariants）

**I1.** L1 / L2 / L3 / L4 四层契约必须保持三向一致；任一不一致即 L4 check 失败，PR 不能合并。

**I2.** Phase 1 完成后，所有一级 + 二级包都有 `README.md` + `pyproject.toml` 段 + `import-linter` 规则。少一个即不通过 L4 check。

**I3.** Phase 2 完成后，仓库内**不存在** `lca.infrastructure` / `lca.cognition` / `lca.layer2_runtime` / `lca.layer3_agent` / `lca.layer4_app` 五个旧名（grep 全仓库为零）。`lca.harness` / `lca.plugins` / `lca.contracts` / `gateway` 不变。

**I4.** Phase 3 完成后，新提交的 Python 文件名**不匹配** filename blacklist（`util` / `helper` / `manager` / `impl` / `common` / `misc`）。匹配的文件必须先在对应包 L2 段声明 `filename_whitelist` 或在仓库根 `legacy_blacklist.txt` 中登记。

**I5.** 三阶段中任一阶段的 CI 强制点（见 §7）必须在该阶段**进入**之前就位；CI 工具本身（`lint-imports` / `scripts/check_package_contracts.py` / `scripts/check_filename_boundaries.py`）必须先存在并能运行。

**I6.** 所有受影响的下游路径（`profiles/*.yaml` 硬编码路径、`deploy/lobehub/patches/`、`docs/` 引用、`tests/` import）必须在同一组 PR 内同步更新；不出现"代码已迁、文档未迁"的中间态。

**I7.** `lobehub-ui/` 和 `vendor/` 在三阶段中**只读**。`lobehub-ui` 的 patches 由 `deploy/lobehub/patches/` 同步；`vendor/` 的更新必须走 ADR + 单独升级流程，不在三阶段工作范围内。

**I8.** 闭集纪律（C1–C7 + AGENTS.md §7）不因重构而放松：所有路径/契约/事件词表变更必须先有 ADR，CI 必绿，公共入口清单必更新。

---

## 3. 整体架构

### 3.1 三阶段依赖图

```
                  ┌──────────────────────┐
                  │ 已有约束（baseline） │
                  │ - 5 层 import-linter │
                  │ - 73 个 ADR          │
                  │ - AGENTS.md          │
                  │ - 30+ check_*.py     │
                  └──────────┬───────────┘
                             │
                             ▼
        ┌────────────────────────────────────┐
        │ Phase 1: 包契约显式化              │
        │  L1 README.md（30+ 个）            │
        │  L2 pyproject 段（30+ 个）         │
        │  L3 import-linter 新增 ~30 条      │
        │  L4 check_package_contracts.py    │
        │                                    │
        │  验收: L4 check 全绿               │
        └────────────────┬───────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │ Phase 2: 目录语义化                │
        │  layer0/1/2/3/4 → infrastructure/  │
        │  cognition/runtime/agent/          │
        │  application                       │
        │  ADR-0104 + 原子切换               │
        │  CHANGELOG breaking changes        │
        │                                    │
        │  验收: 全仓库无旧名；CI 全绿       │
        └────────────────┬───────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │ Phase 3: 命名规范自动化            │
        │  filename linter (warning)         │
        │  legacy_blacklist + whitelist      │
        │  与 L1 公共入口联动                │
        │  季度清理 → error                  │
        │                                    │
        │  验收: 新代码 error；已存 warning  │
        └────────────────────────────────────┘
```

### 3.2 L1–L4 在三阶段中的演进

| 闸口 | Phase 1 后 | Phase 2 后 | Phase 3 后 |
|---|---|---|---|
| **L1 README** | 30+ 新增（每个一级 + 二级包） | 30+ 文件路径重命名；内容微调（"依赖"段指向新名） | 30+ 补"公共入口"段；新增"filename 约束"段 |
| **L2 pyproject** | 30+ 新增 `[tool.lca.package_contracts.*]` 段 | 30+ 段中 `forbidden_dependencies` 路径改为新名 | 30+ 段新增 `filename_blacklist` / `filename_whitelist` 字段 |
| **L3 import-linter** | 现有 5 条 + 新增 ~30 条 `forbidden` + `independence` | 5 条 + ~30 条中的路径全部改为新名 | 不变 |
| **L4 check** | 新增 `scripts/check_package_contracts.py`，L1↔L2↔L3↔实际 import 四向 | 增量检查 `old_name_warning`（应为零） | 增量检查 `filename_violations`（新=0、已存=warning） |

### 3.3 与已有 check 脚本的关系

`scripts/` 已有的 ~30 个 `check_*.py` 在三阶段中**保留**：

- `check_package_boundary.py`（wheel 文件归属）— 不变
- `check_no_any.py` / `check_no_bare_strings.py`（代码规范）— 不变
- `check_protocol_impl.py` / `check_plugin_typing.py`（类型/实现）— 不变
- `check_assembly_purity.py`（装配纯净）— 不变
- `verify_md_links.py` / `verify_doc_budgets.py`（文档）— 不变

新增的 3 个脚本：

- `scripts/check_package_contracts.py`（Phase 1 引入）— L4 主闸口
- `scripts/check_filename_boundaries.py`（Phase 3 引入）— Phase 3 闸口
- `scripts/migrate_layer_rename.py`（Phase 2 引入）— 一次性迁移辅助（可选）

---

## 4. Phase 1 详细设计

### 4.1 9 字段契约模板

每个一级 + 二级包一个 `README.md`，严格按 9 字段填写；同时在 `pyproject.toml` 镜像可机器验证字段。

| # | 字段 | 必填 | pyproject 镜像 | 示例值 |
|---|---|---|---|---|
| 1 | 职责 | ✓ | `responsibility` | "数据契约层：Protocol、枚举、dataclass、事件" |
| 2 | 不负责 | ✓ | `not_responsible_for` | "实现细节、I/O、配置解析" |
| 3 | 输入 | ✓ | （文档） | "接受 DTO: Decision, Action, ContextManifest" |
| 4 | 输出 | ✓ | （文档） | "返回稳定对象或事件，无副作用" |
| 5 | 允许依赖 | ✓ | `allowed_dependencies` | `[]`（lca.contracts 不允许依赖任何层） |
| 6 | 禁止依赖 | ✓ | `forbidden_dependencies` | `["lca.infrastructure", "lca.cognition", ...]` |
| 7 | 副作用 | ✓ | `side_effects` | `[]` 或 `["file:read", "log:emit"]` |
| 8 | 失败语义 | ✓ | （文档） | "可重试：网络超时；不可重试：协议破坏" |
| 9 | 公共入口 | ✓ | `public_api` | `["lca.contracts.models", "lca.contracts.protocols"]` |

### 4.2 L1 README 结构

```markdown
# lca.<package>

> 状态：稳定 | 草稿 | 弃用
> 所有者：<package-owner>
> schema_version: 1.0.0

## 1. 职责
<一句话，本包只负责什么>

## 2. 不负责
<明确列出不负责的范畴>

## 3. 输入
<接受哪些 DTO / Protocol / 命令>

## 4. 输出
<返回哪些稳定对象或事件>

## 5. 允许依赖
<与 pyproject.allowed_dependencies 镜像>

## 6. 禁止依赖
<与 pyproject.forbidden_dependencies 镜像>

## 7. 副作用
<文件 / 网络 / 时间 / 随机数 / 进程 / 日志>

## 8. 失败语义
<错误码、可重试性、补偿方式、可观测字段>

## 9. 公共入口
<外部可 import 的模块和符号清单，Python 用 __all__ 镜像>
```

文件路径：`lca/<package>/README.md` 或 `lca/<package>/<subpackage>/README.md`。每节 1 段，≤200 字。

### 4.3 L2 pyproject 段结构

```toml
[tool.lca.package_contracts."lca.contracts"]
responsibility = "数据契约层：Protocol、枚举、dataclass、事件"
not_responsible_for = "实现细节、I/O、配置解析"
allowed_dependencies = []
forbidden_dependencies = [
    "lca.infrastructure",
    "lca.cognition",
    "lca.layer2_runtime",
    "lca.layer3_agent",
    "lca.layer4_app",
    "lca.harness",
    "lca.plugins",
]
side_effects = []
public_api = ["lca.contracts.models", "lca.contracts.protocols"]
schema_version = "1.0.0"
```

Phase 2 后 forbidden_dependencies 路径改新名；Phase 3 后新增 `filename_blacklist` / `filename_whitelist` 字段。

### 4.4 L3 import-linter 新增规则

现有 5 条 contracts 保留：

1. `layers`: 5 层严格单向
2. `forbidden`: 下层禁依赖 L4
3. `forbidden`: contracts 禁依赖任何实现
4. `forbidden`: harness 禁依赖 L1–L4
5. `forbidden`: plugins 禁依赖 gateway

新增规则（Phase 1 期间）：

- 每个二级包一条 `forbidden`（如 `lca.contracts.atom` 禁依赖 `lca.infrastructure.llm`），约 30 条
- `independence` 规则：`lca.plugins.*` 同层互不依赖（如 `lca.plugins.perceive` 与 `lca.plugins.memory` 互不依赖）

### 4.5 L4 check 脚本骨架

```python
# scripts/check_package_contracts.py
# 验证 L1 README / L2 pyproject / L3 import-linter / 实际 import 四向一致

def check_l1_readme_exists(root: Path) -> list[Issue]: ...
def check_l2_pyproject_section(root: Path, package: str) -> list[Issue]: ...
def check_l3_import_linter_rules(root: Path) -> list[Issue]: ...
def check_actual_imports(root: Path, package: str) -> list[Issue]: ...
def cross_check_l1_l2(root: Path) -> list[Issue]: ...
def cross_check_l2_l3(root: Path) -> list[Issue]: ...
def cross_check_l3_actual(root: Path) -> list[Issue]: ...
def main() -> int:  # exit 0 if all pass, 1 otherwise
    ...
```

实现要点：
- L1 解析：用 markdown 解析器（`markdown-it-py`）定位 9 个 ## 段
- L2 解析：用 `tomllib` 读 `pyproject.toml`
- L3 解析：调 `uv run lint-imports --json` 或直接解析 `.importlinter` 配置文件
- 实际 import：用 `ast` 扫描每个 `.py` 文件的 import 语句
- 失败时输出 diff + 修复建议

### 4.6 30+ 包的清单（Phase 1 目标）

| 一级包 | 二级包 | 数量 |
|---|---|---|
| `lca.contracts` | atoms, models.core, models.observability, models.team, observability, protocols, mechanisms, harness | 8 |
| `lca.infrastructure` | llm, llm_adapter, tools, sandbox, observability, state_store, search, skills, credentials, transport, workspace, ops, plane, host_runtime, attachment, device_gateway, dsh, learning, text, computer, capability | 21 |
| `lca.cognition` | brain, body, memory, sensors, collaboration, member_status | 6 |
| `lca.runtime` | agent_runtime, outcome_policies | 2 |
| `lca.agent` | orchestration_strategies | 1 |
| `lca.application` | （无子包，全部在根） | 1 |
| `lca.harness` | agent, command, declarative, diagnostics, middleware, observability, profile, projection, session, skills, subagents, workflow, sdk | 13 |
| `lca.plugins` | body, brain, bundles, collaboration, compose, composer, control_contributions, creator, critic, gates, graph_nodes, insight, learning, loop_drivers, memory, perceive, phase_edges, phase_executors, phase_policies, phase_topology, profile, providers, reasoner, registries, roles, runtime, seam_definitions, sensors, skill, state, strategies, synthesizer, team_lead, think, tools | 34 |
| `gateway` | device_gateway, plugins, runs | 3 |

合计约 **89 个**包（每个一份 README + pyproject 段 + import-linter 规则）。

> 注：实际清单以实施时 `list_dir` 输出为准；上方数字为估算。

### 4.7 Phase 1 验收标准

- [ ] 89 个 README.md 创建完毕，9 字段齐全
- [ ] 89 个 `[tool.lca.package_contracts.*]` 段在 `pyproject.toml` 创建
- [ ] ~30 条新 `forbidden` + `independence` 规则在 `pyproject.toml [tool.importlinter]` 创建
- [ ] `scripts/check_package_contracts.py` 实施完毕
- [ ] L4 check 跑通：L1↔L2↔L3↔实际 import 四向全绿
- [ ] 既有 CI（`lint-imports` / `mypy lca` / `pytest` / `vulture`）保持绿
- [ ] 在 `docs/architecture/checks.md` 添加 `check_package_contracts.py` 说明

---

## 5. Phase 2 详细设计

### 5.1 旧→新映射

| 旧 | 新 | 状态 |
|---|---|---|
| `lca.infrastructure` | `lca.infrastructure` | 重命名 |
| `lca.cognition` | `lca.cognition` | 重命名 |
| `lca.layer2_runtime` | `lca.runtime` | 重命名 |
| `lca.layer3_agent` | `lca.agent` | 重命名 |
| `lca.layer4_app` | `lca.application` | 重命名 |
| `lca.harness` | `lca.harness` | 不变 |
| `lca.plugins` | `lca.plugins` | 不变 |
| `lca.contracts` | `lca.contracts` | 不变 |
| `gateway` | `gateway` | 不变 |

### 5.2 ADR-0104 草案骨架

`docs/adr/0104-semantic-layer-rename.md`：

```markdown
# ADR-0104: lca 一级包名语义化

## 状态
Proposed → Accepted（PR 合并后）

## 背景
（layer0/1/2/3/4 编号层难以表达职责，新人需要先背顺序再查 ADR）

## 决策
（一次性切换到语义名，无兼容期；保留 lca.harness / lca.plugins / lca.contracts / gateway）

## 影响面盘点
- 代码层：所有 lca.layer* import 改新名（约 N 处）
- 配置层：pyproject.toml import-linter contracts layers
- 文档层：docs/AGENTS.md, docs/specs/, docs/adr/, docs/design/, docs/architecture/
- Profile：profiles/*.yaml（若硬编码路径）
- Plugin 内部：lca/plugins/（若引用）
- 部署：deploy/lobehub/patches/
- 测试：tests/（全量）

## 原子切换清单
（精确列出：哪些文件必须同 PR 改）

## 回退策略
（git revert 整组 PR，因为 git mv 与 import 同步改不可单独 revert）

## 关联
- Phase 1 完成（L4 check 绿）作为前置
- Phase 3（filename linter）作为后续
```

### 5.3 原子切换清单（执行细则）

必须同 PR 改：

1. **代码层**：`grep -r "lca\.layer" lca/ gateway/ tests/ -l` 输出全部更新 import
2. **配置层**：`pyproject.toml` 的 `[tool.importlinter.contracts]` 中 layers 列表改新名
3. **文档层**：`docs/AGENTS.md` §2 仓库地图、`docs/specs/naming-conventions.md` 段尾说明、`docs/adr/0001-five-layer-separation.md` 引用、`docs/design/*` 全部提及 `layer0/1/2/3/4` 的位置、`docs/architecture/optimization-iterations.md`
4. **Profile**：`grep -r "lca\.layer" profiles/` 输出全部更新
5. **Plugin 内部**：`grep -r "lca\.layer" lca/plugins/` 输出全部更新
6. **部署**：`grep -r "lca\.layer" deploy/lobehub/patches/` 输出全部更新；`deploy/lobehub/engine.py` 同步
7. **测试**：`grep -r "lca\.layer" tests/` 输出全部更新
8. **ADR 自身**：`docs/adr/0104-semantic-layer-rename.md` 添加 Accepted 时间戳
9. **CHANGELOG**：根 `CHANGELOG.md` 新增 Breaking Changes 段
10. **root AGENTS.md §3** 的层依赖图

辅助脚本：`scripts/migrate_layer_rename.py`（可选），自动跑 `git mv` + 改 import + 改 import-linter contracts。脚本需 dry-run 模式，PR 描述必须包含 dry-run 输出 diff。

### 5.4 CHANGELOG 模板

```markdown
## [Unreleased] - 2026-XX-XX

### Breaking Changes
- `lca.infrastructure` → `lca.infrastructure`
- `lca.cognition` → `lca.cognition`
- `lca.layer2_runtime` → `lca.runtime`
- `lca.layer3_agent` → `lca.agent`
- `lca.layer4_app` → `lca.application`

### Migration
- 迁移脚本（可选）：`scripts/migrate_layer_rename.py`
- 影响面：
  - Profile YAML：通常不需改（profile 引用 `lca.contracts.*` 或 `lca.harness.plugin_api`，不直接 import `lca.layer*`）
  - Plugin 开发者：所有 `from lca.layer*` import 改新名
  - LobeHub patches：已在 `deploy/lobehub/patches/` 同步更新
  - 外部 SDK 消费方：参考 `packages/gateway-client/` 与 `packages/lca-cli/` 的版本同步
```

### 5.5 Phase 2 验收标准

- [ ] ADR-0104 Accepted
- [ ] 全仓库 `grep -r "lca\.layer[0-4]_" lca/ gateway/ tests/ profiles/ deploy/ docs/` 输出为空
- [ ] 五个新名（`lca.infrastructure` / `lca.cognition` / `lca.runtime` / `lca.agent` / `lca.application`）存在并工作
- [ ] `pyproject.toml` import-linter layers 改为新名
- [ ] 所有 L1 README 段 5/6（依赖允许/禁止）路径更新
- [ ] 所有 L2 pyproject 段 forbidden_dependencies 路径更新
- [ ] L4 check 跑通且 `old_name_warning` 段为 0
- [ ] 既有 CI 全绿
- [ ] `CHANGELOG.md` 包含 Breaking Changes 段
- [ ] 至少 1 个完整 E2E 测试（`uv run pytest tests/e2e/ -q`）通过

---

## 6. Phase 3 详细设计

### 6.1 filename blacklist 与 whitelist

**默认 blacklist**（禁新建）：

| 模式 | 原因 |
|---|---|
| `*util*.py` | 业界最常见反模式，定义不清晰 |
| `*helper*.py` | 同上 |
| `*manager*.py` | 同上（项目已用 `Coordinator` 替代） |
| `*impl*.py` | `Adapter` 替代（见 `naming-conventions.md`） |
| `*common*.py` | "common" 是垃圾桶 |
| `*misc*.py` | 同上 |

**默认 whitelist**（blacklist 模式但允许）：

| 模式 | 原因 |
|---|---|
| `lca/contracts/__init__.py` | 公共入口聚合 |
| `lca/contracts/atoms/__init__.py` | 公共入口聚合 |
| `lca/harness/__init__.py` | 公共入口聚合 |
| `lca/plugins/__init__.py` | 公共入口聚合 |
| `__init__.py`（一般情况） | Python 包标识 |

**包级 whitelist**（L2 段可覆盖）：

```toml
[tool.lca.package_contracts."lca.infrastructure.llm"]
filename_whitelist = ["llm_resolver.py"]  # 例：保留历史命名
```

### 6.2 L4 check 脚本

新增 `scripts/check_filename_boundaries.py`：

- 扫所有新建的 `.py` 文件
- 与 blacklist + whitelist 比对
- 命中 blacklist 且未在 whitelist：error（CI 阻塞）
- 命中 blacklist 且在 `legacy_blacklist.txt`：warning（CI 不阻塞，PR 评论标记）
- 输出 diff + 修复建议

### 6.3 legacy_blacklist 机制

仓库根 `legacy_blacklist.txt`：

```text
# 已有违规文件名清单，新代码不可重复
# 格式：<relative_path>  # <reason + introduced_in>
lca/layer0_infra/observability/trace_tool.py  # 历史命名，Phase 3 不强制改
```

每个季度清理：把稳定的（即 N 季度无 PR 涉及）从 `legacy_blacklist.txt` 移除并实际改名。

### 6.4 与 L1 公共入口段联动

- L1 README 段 9（公共入口）列合法 `__init__.py` 导出
- L4 check 验证 `__init__.py` 的 `__all__` 与 L1 段 9 一致
- 防"包内有人加新公共符号但没更新 README"

### 6.5 Phase 3 验收标准

- [ ] `scripts/check_filename_boundaries.py` 实施完毕
- [ ] 仓库根 `legacy_blacklist.txt` 创建
- [ ] 所有 L2 段新增 `filename_blacklist` 字段（如有特别声明）
- [ ] 新代码命中 blacklist：CI 报错
- [ ] 已存违规：CI warning，PR 评论标记
- [ ] L1 README 段 9 + `__init__.py.__all__` 一致性检查通过
- [ ] 既有 CI 保持绿

---

## 7. CI 强制点时间线

| 时间 | 强制点 | 状态 |
|---|---|---|
| Phase 1 进行中 | L4 check 存在但**不阻塞** | 警告 |
| Phase 1 完成 | L4 check **必须绿** | 错误 |
| Phase 2 进行中 | CI **每步必须绿** | 错误 |
| Phase 2 完成 | 所有 L3 import-linter contracts 改新名 | 错误 |
| Phase 3 进行中 | filename linter **warning** | 警告 |
| Phase 3 完成 | filename linter **error** | 错误 |
| Phase 3 完成 + 1 季度 | legacy_blacklist 季度清理升级 | 错误 |

每一阶段的"进入"前必须确认：上一阶段的强制点已就位 + L4 check 绿 + 既有 CI 绿。

---

## 8. 风险与回退

| 阶段 | 风险 | 缓解 | 回退点 |
|---|---|---|---|
| Phase 1 | 89 个契约文档维护负担 | 模板 + L4 自动化 | L4 失败只报错，逐包补充；可分批 PR |
| Phase 2 | 一次切换破坏下游 | CHANGELOG + 迁移指南 + ADR | 必须独立分支；失败 `git revert` 整组 PR |
| Phase 2 | import-linter contracts 改错 | dry-run + 预演分支 | 立即 revert，文档记录教训 |
| Phase 3 | 误判历史文件 | legacy_blacklist + 包级 whitelist | 误判时加 whitelist 条目，立即生效 |
| Phase 3 | legacy_blacklist 膨胀 | 季度清理 + 强制改名 | 清理本身可独立 PR |

### 8.1 不可逆操作清单

- **Phase 2 的 `git mv` 不可单独 revert**（因为 import 也同步改了）。必须整组 revert。建议先用 `git revert -m 1 <merge-commit>` 而非逐文件 revert。
- **Phase 3 的 legacy_blacklist 升级 error 后，已升级的不可回退到 warning**（防"反复横跳"破坏纪律）。如果发现误升级，必须实际改名而非恢复 warning。
- **AGENTS.md §3 层依赖图**：Phase 2 完成后必须更新；更新前的旧版被视为过时。

### 8.2 测试策略

- 每阶段完成前：`uv run ruff check --fix . && uv run ruff format . && uv run lint-imports && uv run mypy lca && uv run pytest` 全绿
- Phase 2 额外：至少 1 个 E2E 测试通过
- Phase 3 额外：filename linter 自身必须单元测试覆盖（黑/白名单、legacy 行为）

---

## 9. ADR 关联

需要新增的 ADR（按顺序）：

1. **ADR-0104: lca 一级包名语义化**（Phase 2 前置）— 一次性切换到语义名，无兼容期
2. **ADR-0105: lca 4 层契约执行栈**（Phase 1 前置）— L1–L4 机制正式化

不需要新增 ADR（已存在）：

- ADR-0001（5 层单向）— Phase 2 后变成"5 个语义层"单向
- ADR-0004（Protocol-First）
- ADR-0005（Composition Root L4）
- ADR-0015（contracts 无行为类）
- ADR-0037（Journal-as-Truth）
- ADR-0072（Null 默认纪律）

需要更新的 ADR：

- ADR-0001：层名从 `layer0/1/2/3/4` 改为 `infrastructure/cognition/runtime/agent/application`，保留原 ADR 作为历史档案，新增 ADR-0104 替代

---

## 10. 验收标准（总体）

整体三阶段完成的判定：

- [ ] Phase 1、Phase 2、Phase 3 各自的验收标准全部勾选
- [ ] 全仓库 `grep -r "lca\.layer[0-4]_" lca/ gateway/ tests/ profiles/ deploy/ docs/` 输出为空
- [ ] 全仓库新代码不含 filename blacklist 命中
- [ ] L4 check 跑通且四个一致性维度全绿
- [ ] 既有 CI（lint-imports / mypy / pytest / vulture / 30+ check_*.py）全绿
- [ ] 至少 1 个 E2E 测试通过
- [ ] 73+ 个 ADR 数量新增 2 个（ADR-0104、ADR-0105）
- [ ] `CHANGELOG.md` 包含 Phase 2 的 Breaking Changes 段
- [ ] 至少 1 次向外部消费方（profile 作者、plugin 作者、LobeHub patch 维护者）的迁移通知

---

## 11. 参考

- AGENTS.md §3 五层单向依赖 + §5 Team 编码规范 + §7 Git 与禁止事项
- ADR-0001（五层单向）、ADR-0004（Protocol-First）、ADR-0005（Composition Root L4）、ADR-0072（Null 默认纪律）
- `docs/specs/naming-conventions.md`（命名规范）
- `docs/specs/documentation-map.md`（文档地图）
- `docs/specs/lca-structured-cognition-guide.md`（结构化认知）
- `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`（认知原语宪法）
- Python Packaging User Guide — [src layout vs flat layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
- import-linter — [Contract types](https://import-linter.readthedocs.io/en/stable/contract_types/)
- ADR GitHub — [Architectural Decision Records](https://adr.github.io/)
- Arc42 架构文档模板 — [Building Block View](https://arc42.org/)
