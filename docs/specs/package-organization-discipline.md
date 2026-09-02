# Package Organization Discipline

> **状态：** Proposed（待 ADR 评审）
> **适用范围：** `lca/`、`gateway/`、`tests/` 下所有 Python 包目录与 `scripts/` 中的 Python 工具。
> **配套文档：** [naming-conventions.md](./naming-conventions.md)（语义后缀）、[harness-spine-spec.md](./harness-spine-spec.md)（运行时骨架）、[2026-08-19-cognitive-primitive-constitution-v3.md](../design/2026-08-19-cognitive-primitive-constitution-v3.md)（认知原语宪法）、[declarative-phase-graph-spec.md](./declarative-phase-graph-spec.md)（声明式阶段图）。
> **治理原则：** 目录是职责边界、不是文件仓库；文件是稳定概念的实现、不是代码容器。

---

## 0. 一句话

把每个 Python 包目录直接包含的 `.py` 文件数锁定在 **≤ 8**，**9–10 预警**，**> 10 必须按 v3 八概念群拆分**，**> 15 必须拆分或提交 ADR 豁免**。代码体积、类长度、函数长度各自有硬上限。任何越界以 ADR 为唯一豁免通道。

---

## 1. 第一原理

| 反模式 | 正解 |
|---|---|
| 目录 = 文件仓库，谁先写谁就堆这里 | 目录 = 一条职责边界的封闭子图 |
| 文件名 = 实现细节（`utils.py`, `helpers.py`, `misc.py`） | 文件名 = 一个稳定的概念名词（`RunStateReducer`, `JournalOtelProjector`） |
| 拆分靠"我新建一个包"冲动 | 拆分依据"职责是否独立成概念"——可以独立命名才能拆 |
| 目录命名沿用旧名词、缩写、jargon | 目录命名对齐 v3 八概念群 + 既有命名规范的语义后缀 |

> 拆分前必须能回答三个问题：(1) 这个新目录的"核心概念"用一个名词短语能说出来吗？(2) 这个名词能写进 ADR 的标题吗？(3) 任何子类能仅凭这个名字被读者大致定位到吗？

---

## 2. 与既有规范的对齐

| 既有约束 | 来源 | 本规范如何衔接 |
|---|---|---|
| 五层单向依赖 | ADR-0001、AGENTS.md §3 | 不变；本规范在每层内加 8/10/15 与认知群对齐 |
| `contracts/` 仅类型与接口 | ADR-0015 | 不变；本规范额外约束 `contracts/` 内的子目录规模 |
| 命名后缀（Protocol/Adapter/Coordinator/Registry/Manifest/Plan） | `naming-conventions.md` | 不变；本规范要求包名与文件名都遵守同一套语义后缀 |
| 插件扩展路径：Protocol → Seam → Provider → Registry → Plugin → Profile/Bundle | AGENTS.md §3 | 不变；本规范要求每个 Seam/Provider 包都按 8/10/15 自我约束 |
| 文件 ≤ 1500 行、方法 ≤ 200 行 | AGENTS.md §5 | 收紧到：文件 ≤ 400 行、类 ≤ 200 行、函数 ≤ 50 行 |
| Plugin-everything 范式 | Harness Spine Spec §0.4 | 不变；本规范给"plugin 目录"一个明确规模上限 |

---

## 3. 8/10/15 规则（核心条款）

### 3.1 直接 `.py` 计数口径

- **计入**：包目录直接子级的 `.py` 文件
- **不计入**：`__init__.py`、`__main__.py`、`tests/` 下的测试文件、`conftest.py`
- **豁免文件**：仅"以目录根名 + 单文件"形式承载包级声明的 `__init__.py`

### 3.2 三档阈值

| 阈值 | 处置 | 提交前检查 |
|---|---|---|
| **≤ 8** | 正常 | 不需要解释 |
| **9–10** | **预警** | PR 描述必须确认无职责混杂；附 `git grep` 证明每个文件对应一个稳定概念 |
| **> 10** | **优先拆分** | 拆分 PR 与功能 PR 解耦；按 v3 八概念群或子职责重切 |
| **> 15** | **必须拆分** | 不接受 "无脑累加"；不豁免时禁止合并；豁免必须提交 ADR |

### 3.3 豁免通道

只有以下两类可以越线：

1. **概念唯一性**：目录对应一个无法进一步拆分的稳定概念（例如 `JournalOtelProjector`、`JournalReducer` 同根，必须放一起）。**这种情况仍要走 ADR 文档化原因**，而非静默保留。
2. **过渡期兼容**：迁移中的目录在 ADR 中标注"过渡态 + 退役时间"。无 ADR 不接受。

任何豁免 ADR 必须在正文显式列出：当前 `.py` 数、拆分目标、迁移 PR 列表、退役日期。

---

## 4. 规模分层约束

下表是项目整体的合理规模上限。**顶层包数突破上限时**，先评估是否还能合并到现有层（不要为新业务强行新开顶层包）。

| 层级 | 建议规模 | 硬上限 | 备注 |
|---|---|---|---|
| `lca/` 顶层业务包 | 5–8 个 | **10 个** | 当前 7 个：`contracts` / `infrastructure` / `cognition` / `runtime` / `agent` / `application` / `harness` |
| 每个业务包的一级子模块 | 3–7 个 | **10 个** | `lca/infrastructure/` 当前 22 个子模块，**已超上限**，需按概念群重组 |
| 每个模块的直接 `.py` | 3–8 个 | **8 个** | 即 8/10/15 规则的目标对象 |
| 单个 `.py` 文件 | 80–250 行 | **400 行**（含注释和空行） | 不含 `__init__.py` 内的纯导入 |
| 单个类 | 50–150 行 | **200 行** | 包含 `__init__` 和 dunder 方法 |
| 单个函数（除 `__init__`/dunder） | 5–30 行 | **50 行** | 嵌套深度 ≤ 4 |
| 单个目录的核心概念数 | 1 个 | — | 例外：拆不出第二个稳定名词，就不要拆 |

---

## 5. 概念群映射（v3 八群对齐）

按照 [v3 认知原语宪法 §3.2](../design/2026-08-19-cognitive-primitive-constitution-v3.md) 与 [结构化认知指南 §3](./lca-structured-cognition-guide.md)，业务包目录优先按以下九群命名。每个群代表一条职责边界：

| 群 | 关键字 | 典型内容 | 当前样例 |
|---|---|---|---|
| **State** | `state`, `snapshot`, `projection` | Reducer、RunState、Projection、Checkpoint | `lca/contracts/models/core/{state,lifecycle,terminal_outcome}.py` |
| **Perceive** | `perceive`, `sense`, `observe` | Sensor、PerceiveHub、ContextManifest | `lca/cognition/sensors/`, `lca/plugins/perceive/` |
| **Think** | `think`, `reason`, `plan`, `reflect` | Brain、Reasoner、Critic、Synthesizer | `lca/cognition/brain/`, `lca/plugins/{brain,reasoner,critic,synthesizer,think}/` |
| **Gate** | `gate`, `policy`, `verdict` | DecisionGate、GateChainComposer、LeadBudgetPolicy | `lca/plugins/gates/`, `lca/cognition/brain/decision_gates/` |
| **Act** | `act`, `execute`, `tool`, `effect` | Body、Tool、SafeExecutor、EffectGateway | `lca/cognition/body/`, `lca/plugins/{body,tools}/`, `lca/infrastructure/tools/` |
| **Memory** | `memory`, `remember`, `retrieval` | MemorySystem、LayeredRetrieval、CompactionPolicy | `lca/cognition/memory/`, `lca/plugins/memory/` |
| **Collaboration** | `team`, `delegate`, `handoff`, `coordination` | Agent、Team、Strategy、DelegationGrant | `lca/agent/`, `lca/plugins/{collaboration,team_lead,strategies}/` |
| **Journal** | `journal`, `event`, `trace`, `telemetry`, `evidence` | RunStore、Projector、Reducer、EvidenceStore | `lca/infrastructure/observability/journal/`, `lca/contracts/observability/` |
| **Composition** | `profile`, `bundle`, `plugin`, `compose`, `boot`, `harness`, `runtime` | Profile Resolver、PluginManifest、Composer、Boot | `lca/harness/{profile,declarative,plugin_api}.py`, `lca/application/`, `lca/plugins/composer/` |

**规则**：新建子包时，名字必须能映射到上述九群之一。映射不到 → 先写 ADR 解释为什么需要新群，再建包。

### 5.1 反模式命名清单（必须改）

| 现名 | 问题 | 建议 |
|---|---|---|
| `lca/infrastructure/plane/` | "plane" 在认知框架中是双平面概念，此处含义冲突 | `lca/infrastructure/runtime_plane/`（执行环境类型：machine/sandbox/office） |
| `lca/infrastructure/text/` | 与本目录真实内容（两个字符串截断工具）不符 | 把 `safe_boundary.py` + `truncate.py` 合并到 `lca/infrastructure/text_util.py` 单文件，或归并到 `lca/infrastructure/observability/narrative/` |
| `lca/infrastructure/ops/` | "ops" 与 `gateway/`、`scripts/` 含义重叠 | 改 `lca/infrastructure/cli/`（明确它是 CLI 命令框架） |
| `lca/plugins/creator/faces/` | `face` 是 persona 库 jargon | 改 `lca/plugins/creator/personas/` |
| `lca/plugins/compose/` vs `composer/` | 1 字母之差，语义差隐藏在 docstring | `compose/` → `lca/plugins/factories/`；`composer/` → 保留，但每个子模块按群命名（`composer/brain/`、`composer/body/`） |
| `lca/plugins/state/` | 名实不符，目录里只有 `stop_policy.py` | 合并到 `lca/plugins/phase_policies/stop_policy.py` |
| `lca/plugins/team_lead/` | 空包（README + 空 `__init__.py`） | 删除；若 `HierarchicalStrategy` 需要专属命名空间，迁到 `lca/plugins/strategies/hierarchical_team_lead.py` |
| `lca/plugins/graph_nodes/`、`phase_edges/`、`phase_executors/`、`phase_policies/`、`phase_topology/` | 五个目录同切"phase graph"概念 | 合并为一个 `lca/plugins/phase_graph/`，按"节点 / 边 / 执行器 / 策略 / 拓扑"分子包 |
| `lca/plugins/seam_definitions/` | "seam" 是架构 jargon，55 个文件难扫 | 改名 `lca/plugins/seams/`；超过 10 个文件时按群分子目录（`seams/{memory,journal,llm,observability}/`） |
| `lca/plugins/registries/` | 只有 1 个文件 + README | 删除；该文件的语义属于 `seams/` 或 `harness/registries/` |
| `lca/plugins/control_contributions/` | 13 个文件按认知动词前缀排列，但目录名不说清 | 改名 `lca/plugins/cognitive_steps/`；每个动词一个子包（`cognitive_steps/act.py`、`cognitive_steps/think.py`），单文件超出 8 时再分子包 |
| `lca/infrastructure/observability/coding_agent_tools/` | 9 个独立工具混在一个目录 | 改 `lca/plugins/tools/diagnostics/`（既然是工具而不是基础设施） |
| `lca/contracts/protocols/` | 53 文件平铺 + 314 行 barrel | 把 8 个 `declarative_*.py` 收到 `declarative/` 子包；`__init__.py` 改成显式 `__all__` |
| `lca/contracts/harness/` | 37 文件平铺 | 按 v3 九群分子目录（`harness/{state,act,collaboration,journal,composition}.py`） |
| `gateway/runs/` | 57 文件平铺 | 拆为 `runs/{api,lifecycle,session,ingest,execute,terminal,doctor,wire,observability}/` 9 个子包 |
| `lca/infrastructure/observability/journal/` | 23 文件平铺 | 拆为 `journal/{engine,otel,console,jsonl,sse,stream,enrichment,backends}/` 8 个子包 |

### 5.2 命名原则（与 `naming-conventions.md` 并行）

包名（目录名）的额外规则：

1. **优先名词或动名词**：`gateway/runs/` 比 `gateway/runner/` 清晰；`journal/otel/` 比 `journal/otel_mapping/` 清晰（后者是文件名）。
2. **避免双重否定和被动语态**：`no_double_encoding.py` → `single_encoding.py`；`unregistered_journal_event_error.py` → `journal_event_must_be_registered.py`（先描述期望态，再加 `Error` 后缀）。
3. **缩写只在领域通用时使用**：`LLM`、`JSONL`、`OTel`、`SSE`、`A2A`、`MCP` 保留；其他缩写必须展开。`lca_computer`、`lca_sandbox`、`plane`、`text` 全部展开。
4. **同名不歧义**：`sandbox/` 与 `lca_sandbox/` 共存是历史债；新代码禁止 "lca_" 前缀。
5. **导出符号与目录一一对应**：目录下导出 `JournalReducer` 时，目录至少要叫 `journal/` 或包含 `journal` 关键字。

文件名补充规则：

1. **文件名 = 单个稳定概念**。`utils.py`、`helpers.py`、`common.py`、`misc.py` 是反模式命名，**禁止新增**；已存在的标记为迁移目标。
2. **测试文件**：`<concept>_test.py` 或目录化 `tests/<module>/test_<aspect>.py`。
3. **类型 / dataclass / Protocol 文件**：与符号同名；不要再加 `models/`、`types/`、`schemas/` 子目录做无信息包装。
4. **Provider / Adapter / Factory 文件**：文件名前缀即符号前缀，例如 `genai_llm.py` 提供 `GenaiLLMAdapter`、`filesystem_evidence_store.py` 提供 `FilesystemEvidenceStore`。

---

## 6. 代码体量硬约束

```yaml
package_direct_py_max: 8       # 8/10/15 规则
package_direct_py_warning: 10
package_direct_py_break: 15
file_loc_max: 400              # 含注释和空行，不含 __init__.py 纯导入
class_loc_max: 200
function_loc_max: 50
nested_depth_max: 4            # AST 静态检查
dir_concept_count_max: 1       # 一个目录一个稳定概念
top_level_pkg_max: 10          # lca/ 下顶层包数
first_level_submodule_max: 10  # 任一包下一级子模块数
```

每个上限都有对应的 CI 检查（见 §10）。

---

## 7. 责任边界规则

### 7.1 一个目录一个核心概念

每个目录的"核心概念"必须能用一个名词短语回答：

```text
❌ lca/plugins/composer/  → 概念 = "Composer"（太多子职责）
✅ lca/plugins/composer/brain/   → 概念 = "Brain Composer"
✅ lca/plugins/composer/runtime/ → 概念 = "Runtime Composer"
```

### 7.2 拆分判断树

```
同目录新增文件时
│
├─ 文件名可以独立成一个名词吗？
│   ├─ 是 → 拆分到子目录或独立包
│   └─ 否 → 进入下一问
│
├─ 它跟现有某个文件是 "插件 × 协议" 配对（如 Provider × Protocol）吗？
│   ├─ 是 → 放进同名子目录（protocols/, providers/）
│   └─ 否 → 进入下一问
│
├─ 它跟现有某个文件属于不同的 v3 概念群？
│   ├─ 是 → 拆到对应概念群子目录
│   └─ 否 → 进入下一问
│
├─ 它是否可以由 < 50 行实现？两个小文件能合并为一个文件吗？
│   ├─ 是 → 合并
│   └─ 否 → 必须拆分（已 ≥ 11 文件则违反 8/10/15）
```

### 7.3 禁止的命名/结构

| 反模式 | 为什么禁止 |
|---|---|
| `utils.py` / `helpers.py` / `common.py` / `misc.py` / `shared.py` | 无信息后缀，等于"懒得命名" |
| `interfaces.py` / `protocols.py` / `types.py` 在业务实现层 | 这些是契约层概念，业务层不应该再有泛化包装 |
| `*_impl.py` / `*_v2.py` 同目录并存 | 同名概念的新版本应替换旧版本；旧版本保留必须带 ADR 豁免 |
| 在 `__init__.py` 用 `__all__ = list(globals())` 自动 barrel | 见 §10.4；每个新符号都隐式变成公共 API |
| `tests/test_<module>.py` 与 `tests/<module>/test_*.py` 同名并存 | 测试发现歧义 |

---

## 8. 豁免机制

### 8.1 流程

1. **发现越线**：CI 报警 → 提交者必须在本 PR 内处理，或引用豁免 ADR。
2. **豁免 ADR 模板**：
   - 标题：`ADR-NNNN: 豁免 <package> 超过 8/10/15 阈值`
   - 必须包含：当前 `.py` 数、阈值、不可拆分的具体原因、迁移计划、退役日期。
3. **豁免有效期限**：≤ 6 个月；过期未迁移视为违规。
4. **同一包最多 1 份活跃豁免 ADR**；多份则旧版本自动失效。

### 8.2 不可豁免

- `lca/contracts/protocols/__init__.py` 用 `globals()` 自动 barrel → **必须改显式 `__all__`**。
- 空包（只有 README + 空 `__init__.py`） → **必须删除或填充**。
- 损坏包（有 `.py` 无 `__init__.py`） → **必须修复**。
- `__init__.py` 不写导出列表却在 contracts/ 内被广泛 import → **必须补 `__all__`**。

---

## 9. CI 门禁

下列检查全部进 `scripts/check_*.py`，并接入 `pyproject.toml` 的 `[tool.pytest.ini_options] markers` 与 ruff custom rule：

| 检查 | 工具 | 阈值 |
|---|---|---|
| 直接 `.py` 计数 | `scripts/check_package_size.py`（新增） | 8 正常 / 10 预警 / 15 越线 |
| `__init__.py` barrel 自动导出 | `scripts/check_no_barrel_glob.py`（新增） | 禁止 `__all__ = list(globals())` |
| `utils.py` / `helpers.py` / `common.py` | `scripts/check_no_utility_modules.py`（新增） | 禁止新增；存量列入迁移 backlog |
| 文件行数 | ruff `max-lines` | 400 |
| 函数 / 类行数 | ruff `max-lines-per-function` 等 | 50 / 200 |
| 嵌套深度 | ruff `max-function-nesting` | 4 |
| 子包命名映射 | `scripts/check_package_noun.py`（新增） | 包名必须能用 v3 概念群关键词解释 |
| 缩写字典 | `scripts/check_known_abbrev.py`（新增） | `LLM`/`JSONL`/`OTel`/`SSE`/`A2A`/`MCP` 允许；其他白名单需 ADR |
| 空包 / 损坏包 | `scripts/check_package_integrity.py`（新增） | 禁止 |
| 测试平铺 | `scripts/check_tests_layout.py`（新增） | `tests/` 下直接 `test_*.py` 数量 ≤ 30；超过按 `tests/{unit,contract,architecture,integration,scenario}/` 落桶 |
| README 脚手架占位 | `scripts/check_readme_filled.py`（新增） | 禁止 `{{inputs}}`、`{{outputs}}`、`待包负责人补充` 等占位符 |

每个脚本输出 `--json` 与默认文本两种格式，纳入 `lca-ops diagnose` 子命令。

---

## 10. 现状盘点（2026-08-30 基线）

> 基于全量审计 `find lca gateway scripts tests -name "*.py" | wc -l` 与 `scripts/check_package_size.py --report` 输出。下面是 **直接 .py 数 ≥ 10** 的目录清单，必须在 Phase 1 处置。

### 10.1 严重越线（> 15，必须拆分或豁免）

| 路径 | 直接 .py | 拆分目标 |
|---|---|---|
| `gateway/runs/` | **57** | `runs/{api,lifecycle,session,ingest,execute,terminal,doctor,wire,observability}/` 9 个子包 |
| `lca/plugins/providers/` | **55** | `providers/{llm,journal,observability,session,phase,runtime,tools,evidence,fact_readers,fact_scorers,event_identity,profile_snapshot,run_ui_encoder,openai_stream_encoder}/`（按协议名分组） |
| `lca/contracts/protocols/` | **53** | `protocols/{declarative,phase_graph,execution,session,observability,journal,memory,team,tool,infra}/` 10 个子包；8 个 `declarative_*.py` 收到 `declarative/` |
| `tests/` | **~165 直接** | `tests/{unit,contract,architecture,integration,scenario,fixtures,smoke}/` 7 个桶；直接 `test_*.py` 不超过 30 |
| `scripts/` | **43** | `scripts/{checks,migrations,scenarios,observability,ci}/` 5 个子目录 |
| `lca/contracts/harness/` | **37** | 按 v3 九群切：`harness/{state,act,collaboration,journal,composition,declarative,evidence,plugin,session,subagent,workflow}/` |
| `lca/plugins/seam_definitions/` | **38** | 改名 `lca/plugins/seams/`；按群切 `seams/{memory,journal,llm,observability,tool,state_store,sandbox,transport}/` |
| `lca/plugins/composer/` | **21** | `composer/{brain,body,perceive,runtime,team,fixtures}/` |
| `lca/infrastructure/observability/journal/` | **23** | `journal/{engine,otel,console,jsonl,sse,stream,enrichment,backends}/` 8 个子包 |

### 10.2 预警（10–15，本季度内评估）

| 路径 | 直接 .py | 备注 |
|---|---|---|
| `lca/infrastructure/observability/` | 28 | 含 `coding_agent_tools/` 9 文件，应迁到 `lca/plugins/tools/diagnostics/` |
| `lca/infrastructure/ops/` | 11 | 改名 `cli/`；`commands/` 子目录已达 12，继续累加 |
| `lca/infrastructure/ops/commands/` | 12 | 拆 `cli/commands/{run,profile,diagnose,journal,plugin}/` |
| `lca/infrastructure/tools/` | 13 + 8 子目录 | 已经按工具分子目录；状态健康 |
| `lca/plugins/phase_executors/` | 10 | 按认知动词拆 `phase_executors/{perceive,think,act,reflect,remember,stop,failure_stop,capabilities,common}.py`（已经是这个布局） |
| `lca/infrastructure/observability/coding_agent_tools/` | 9 | 整目录迁出到 `lca/plugins/tools/diagnostics/` |
| `lca/harness/declarative/` | 25 | 8 个 `phase_*` 文件拆 `declarative/phase_graph/` 子目录 |
| `lca/contracts/observability/` | 20 | 按 v3 群切 `observability/{journal,evidence,cost,diagnostic,event}/` |

### 10.3 命名违规清单（不论文件数，必须改）

| 现路径 | 现名 | 建议 |
|---|---|---|
| `lca/infrastructure/plane/` | 名实冲突 | `lca/infrastructure/runtime_plane/` |
| `lca/infrastructure/text/` | 无 `__init__.py` + 名实不符 | 删目录或合并到 `observability/narrative/` |
| `lca/infrastructure/observability/cost/` | 无 `__init__.py` | 修复或迁到 `journal/cost/` |
| `lca/plugins/memory/` | 无 `__init__.py` | 修复；或合并到 `lca/cognition/memory/` |
| `lca/plugins/creator/` | 空 README-only | 删除；代码迁到 `plugins/composer/personas/` |
| `lca/plugins/team_lead/` | 空 | 删除 |
| `lca/plugins/registries/` | 1 文件 | 删除；该文件迁 `seams/` 或 `harness/registries.py` |
| `lca/plugins/state/` | 名实不符 | 合并到 `phase_policies/` |
| `lca/plugins/graph_nodes/` + 4 个 `phase_*` | 同切同概念 | 合并到 `plugins/phase_graph/` |
| `lca/plugins/compose/` vs `composer/` | 1 字母差 | 改 `compose/` → `factories/` |
| `lca/plugins/seam_definitions/` | jargon + 55 文件 | 改 `seams/` + 分子目录 |
| `lca/harness/sdk/` | 空 | 删除 |
| `lca/runtime/completion/`、`outcome_policies/` | README-only | 删除 |
| `lca/packages/identity/anonymous_user_id/` | 完全空目录 | 删除 |
| `lca/packages/runtime_diagnostics/invariants/src/` | 完全空目录 | 删除 |
| `lca/infrastructure/observability/exporters/` | 0 文件 + 文档已声明迁移完成 | 删除 |
| `lca/infrastructure/observability/narrative/` | 4 文件 + 文档已声明大部分已迁 | 评估保留理由 |
| `lca/contracts/protocols/__init__.py` | 314 行自动 barrel | 改显式 `__all__` |

### 10.4 README 脚手架失效

`lca/infrastructure/`、`lca/plugins/`、`lca/harness/`、`lca/contracts/`、`lca/cognition/` 下约 **30 个 README.md 是同一份脚手架**，含 `{{inputs}}`、`{{outputs}}`、`{{failure_semantics}}` 等未填充占位符。

处置：
- 标记为 `<!-- scaffolded: needs_owner -->`，CI 阻断新占位符。
- 一次性任务：挑选 5–8 个高曝光包，由负责人补完（输入/输出/失败语义/对外契约）；其余删除 README 或改单行 `"""docstring"""`。

---

## 11. 拆分模板

### 11.1 平铺 → 子包（journal 为例）

**当前**（23 文件平铺）：

```
lca/infrastructure/observability/journal/
├── console_projector.py
├── console_render.py
├── engine.py
├── event_enrichers.py
├── fact_stream_projector.py
├── __init__.py
├── journal_io.py
├── jsonl_projector.py
├── live_tail.py
├── narrative_sidecar.py
├── otel_genai_mapping.py
├── otel_mapping.py
├── otel_projector.py
├── otel_span_index.py
├── process.py
├── reducer.py
├── sequence_diagram.py
├── serialization.py
├── sse_frames.py
├── table_renderer.py
└── backends/{filesystem.py, memory.py}
```

**目标**（按输出形态拆 8 个子包 + 1 引擎根）：

```
lca/infrastructure/observability/journal/
├── __init__.py                 # 公共入口
├── engine.py                   # RunStore, process, reducer, serialization, journal_io
├── enrichment/
│   ├── __init__.py
│   └── event_enrichers.py
├── otel/
│   ├── __init__.py
│   ├── projector.py
│   ├── mapping.py
│   ├── genai_mapping.py
│   └── span_index.py
├── console/
│   ├── __init__.py
│   ├── projector.py
│   ├── render.py
│   ├── sequence_diagram.py
│   └── table.py
├── jsonl/
│   ├── __init__.py
│   └── projector.py
├── sse/
│   ├── __init__.py
│   └── frames.py
├── stream/
│   ├── __init__.py
│   ├── fact_stream.py       # 2026-09-02 删除（ADR-2026-09-02-i17-stream-align §A）
│   ├── live_tail.py
│   └── narrative_sidecar.py # 2026-09-02 由 StepNarrativeWriter 接管
└── backends/
    ├── __init__.py
    ├── filesystem.py
    └── memory.py
```

每个子包 ≤ 4 个 `.py` 文件，最深处 3 层。

### 11.2 平铺 → 子包（gateway/runs 为例）

**当前**：57 文件平铺。

**目标**（按职责切 10 个子包）：

```
gateway/runs/
├── __init__.py                 # Run aggregate docstring + 公共 re-export
├── README.md
├── api/                        # HTTP / SSE 入口
│   ├── __init__.py
│   ├── routes.py
│   ├── command_endpoints.py
│   ├── query_endpoints.py
│   ├── attachment_staging.py
│   └── file_reference_parsing.py
├── lifecycle/                  # Run 生命周期与可恢复
│   ├── __init__.py
│   ├── lifecycle.py
│   ├── runnable_assembly.py
│   ├── run_context_factory.py
│   └── export_disposal.py
├── session/                    # Session 维度
│   ├── __init__.py
│   ├── builder.py              # session_builder.py
│   ├── setup.py                # session_setup.py + session_setup_types.py
│   ├── session.py
│   ├── health.py
│   ├── index.py
│   ├── projection.py
│   ├── diagnostics.py
│   └── message.py              # message_history.py + message_text.py + intent.py
├── ingest/                     # 摄取管道
│   ├── __init__.py
│   ├── ingest.py
│   ├── cache.py
│   ├── fetcher.py
│   ├── integrity.py
│   ├── models.py
│   ├── policy.py
│   ├── service.py
│   └── ingress.py
├── execute/                    # 执行路径
│   ├── __init__.py
│   ├── execute.py
│   ├── scheduling.py
│   ├── environment_bindings.py
│   ├── execution_environment.py
│   └── loop_drivers.py
├── terminal/                   # 终态
│   ├── __init__.py
│   ├── terminalizer.py
│   ├── materialization.py
│   ├── status.py
│   ├── outcome.py              # outcome_application.py
│   ├── failure.py              # failure_recording.py
│   ├── legacy.py               # legacy_adapter.py + live_compat.py + port.py
│   └── registry.py             # registry_commands.py + registry_queries.py
├── doctor/                     # 自检
│   ├── __init__.py
│   ├── doctor.py
│   ├── journal.py
│   ├── legacy.py
│   ├── models.py
│   └── session.py
├── observability/              # 观测绑定
│   ├── __init__.py
│   ├── binding.py
│   ├── journal_projection_binding.py
│   ├── evidence.py
│   ├── artifact_closure.py
│   ├── error_presentation.py
│   └── identity.py
└── wire/                       # wire / port / command envelope
    ├── __init__.py
    ├── wire.py
    └── command_envelope.py
```

每个子包 ≤ 7 文件，深度 2 层。

### 11.3 多个 protocol 文件按群落分组（contracts/protocols 为例）

**当前**：53 文件平铺 + 314 行自动 barrel。

**目标**（按 v3 九群切 10 个子包）：

```
lca/contracts/protocols/
├── __init__.py                 # 显式 __all__，无 globals() 自动导出
├── README.md
├── state/                      # State/Plan/Reducer
│   ├── __init__.py
│   ├── state.py
│   ├── plan.py
│   ├── reducer.py
│   ├── scope_plan.py
│   └── delta_handler.py
├── perceive/                   # Perceive / Sensor / ContextManifest
│   ├── __init__.py
│   ├── perceive.py
│   └── capability_plan.py
├── think/                      # Brain / Reasoner / Reflect
│   ├── __init__.py
│   ├── cognition.py
│   ├── reasoning.py
│   └── learning.py
├── gate/                       # DecisionGate / LeadBudget / ControlVerdict
│   ├── __init__.py
│   ├── gate.py
│   ├── gate_chain_composer.py
│   ├── decision_classifier.py
│   ├── control_verdict.py
│   └── lead_budget_policy.py
├── act/                        # Body / Effect / Tool
│   ├── __init__.py
│   ├── action.py
│   ├── action_handler.py
│   ├── effect_handler.py
│   ├── embodiment.py
│   └── tool_pipeline.py
├── memory/
│   ├── __init__.py
│   └── memory.py
├── collaboration/              # Team / Orchestration
│   ├── __init__.py
│   ├── agent.py
│   ├── orchestration.py
│   ├── team_seam.py
│   └── casting.py
├── journal/                    # Journal / Idempotency / Spec
│   ├── __init__.py
│   ├── journal.py
│   ├── idempotency.py
│   ├── spec.py
│   └── event_descriptor.py
├── session/                    # Session / Turn / Resume
│   ├── __init__.py
│   ├── session_turn.py
│   ├── session_persistence.py
│   ├── session_command_ledger.py
│   ├── resume_input.py
│   └── run_mode.py
└── declarative/                # 8 个 declarative_*.py 集中
    ├── __init__.py
    ├── capability.py
    ├── common.py
    ├── execution.py
    ├── fault_tolerance.py
    ├── graph.py
    ├── phase_graph.py
    └── plugin.py
```

每个子包 ≤ 8 文件；显式 `__all__`；`__init__.py` 不再自动 barrel。

---

## 12. 迁移路线（按 ROI 排序）

### Phase A：零风险清扫（1 周内）

1. 删除 5 个空目录树：`lca/packages/identity/anonymous_user_id/`、`lca/packages/runtime_diagnostics/invariants/src/`、`lca/runtime/completion/`、`lca/runtime/outcome_policies/`、`lca/harness/sdk/`。
2. 删除 3 个 README-only 包：`lca/plugins/team_lead/`、`lca/plugins/creator/`（迁出仅有的 2 文件）、`lca/infrastructure/observability/exporters/`。
3. 修复 3 个损坏包：`lca/infrastructure/text/`、`lca/infrastructure/observability/cost/`、`lca/plugins/memory/`（补 `__init__.py` 或迁出）。
4. `lca/contracts/protocols/__init__.py` 改显式 `__all__`。

**预期**：认知负担热点消失 60%；越线目录减少 5 个。

### Phase B：超大目录拆分（3 周内，并行）

按 §11 模板执行，每个目录一个 PR：
1. `gateway/runs/`（57 → 10 子包）
2. `lca/infrastructure/observability/journal/`（23 → 8 子包）
3. `lca/contracts/protocols/`（53 → 10 子包）
4. `lca/plugins/seam_definitions/` → `seams/`（55 → 8 子包）
5. `lca/plugins/providers/`（66 → 14 子包）
6. `lca/contracts/harness/`（37 → 11 子包）
7. `lca/plugins/composer/`（29 → 6 子包）
8. `lca/harness/declarative/`（25 → 拆 `phase_graph/` 子包）

每个 PR 必须附带：
- 改动列表与 import 路径映射表
- 自动化迁移脚本（如 `scripts/migrate_*.py`）
- ruff/lint-imports/mypy 全绿
- 相关 tests 全绿

### Phase C：命名规范收敛（2 周）

1. 改 `lca/infrastructure/plane/` → `runtime_plane/`。
2. 改 `lca/plugins/creator/faces/` → `personas/`。
3. 合并 `lca/plugins/graph_nodes/` + 4 个 `phase_*` → `phase_graph/`。
4. 改 `lca/plugins/compose/` → `factories/`。
5. 改 `lca/infrastructure/ops/` → `cli/`。
6. 删 `lca/plugins/registries/`、`lca/plugins/state/`。
7. 迁移 `lca/infrastructure/observability/coding_agent_tools/` → `lca/plugins/tools/diagnostics/`。

### Phase D：CI 门禁落地（1 周）

1. 新增 `scripts/check_package_size.py`、`scripts/check_no_barrel_glob.py`、`scripts/check_no_utility_modules.py`、`scripts/check_package_noun.py`、`scripts/check_known_abbrev.py`、`scripts/check_package_integrity.py`、`scripts/check_tests_layout.py`、`scripts/check_readme_filled.py`。
2. 把所有检查接入 `lca-ops diagnose package-organization`。
3. 在 CI 主流程增加 `package-organization` job，作为合并前置。

### Phase E：长尾收尾（持续）

- 把剩余 `helpers.py`、`utils.py`、`misc.py` 全部清理或改名。
- 补齐 README：先挑 5 个高曝光包（`lca/contracts/`、`lca/infrastructure/observability/`、`lca/plugins/composer/`、`lca/cognition/brain/`、`lca/harness/declarative/`）。
- 在 ADR 中归档所有"豁免"和"过渡态"。

---

## 13. 附录 A：快速自检清单

每次新增 Python 文件或目录前，对照下面 6 条：

- [ ] **目录数**：父目录直接 `.py` 数 ≤ 8？
- [ ] **概念数**：新目录能用 1 个名词短语解释吗？
- [ ] **命名**：避免 `utils` / `helpers` / `common` / `misc` / 缩写？
- [ ] **行数**：新文件 < 250 行？
- [ ] **群映射**：目录名能映射到 v3 九群之一？
- [ ] **导出**：在新包的 `__init__.py` 显式 `__all__` 而不是 `globals()`？

任一项回答"否" → 不要提交，先调整。

---

## 14. 附录 B：与其他规范文档的索引

| 主题 | 文档 |
|---|---|
| 命名后缀 | `docs/specs/naming-conventions.md` |
| 运行时骨架 | `docs/specs/harness-spine-spec.md` |
| 认知原语宪法 | `docs/design/2026-08-19-cognitive-primitive-constitution-v3.md` |
| 声明式阶段图 | `docs/specs/declarative-phase-graph-spec.md` |
| 结构化认知指南 | `docs/specs/lca-structured-cognition-guide.md` |
| Run 实时流 | `docs/specs/run-live.md` |
| 工具失败恢复 | `docs/specs/tool-failure-recovery.md` |
| 术语表 | `docs/specs/glossary.md` |
| ADR 索引 | `docs/adr/`（74 份） |
