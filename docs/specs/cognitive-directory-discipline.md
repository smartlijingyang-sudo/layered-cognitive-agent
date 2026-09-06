# Cognitive Directory Discipline — 图书馆式目录宪法

> **状态：** Accepted（ADR-0195 延伸）  
> **配套：** [platform-directory-architecture.md](platform-directory-architecture.md) · [package-organization-discipline.md](package-organization-discipline.md) · [naming-constitution.md](../design/naming-constitution.md)

本文定义 LCA 代码库的**目录认知可靠性**：给人读、也给 agent 读。顺着路径应能回答三个问题——**这个目录管什么？这个文件是什么概念？和同目录兄弟是否同一职责族？**

---

## 0. 一句话

**每个目录 ≤5 个直接 `.py`；每个文件 ≤300 行（硬顶 400）；文件名在目录语境下自解释；禁止把临时实现堆在「顺手的旧目录」。**

---

## 1. 第一性原理

| 反模式 | 正解 |
|---|---|
| 目录 = 文件仓库 | 目录 = 图书馆的一层书架（一个主题） |
| `journal_append.py` 放在任意包 | 路径即语义：`session/append.py` 或 `commit/act_journal.py` |
| 同目录 15 个平铺 `.py` | 按子主题再分一层，每层仍 ≤5 |
| 800 行「模块」 | 拆成多个名词文件，或分子目录 |
| agent 新建 `utils_emit_helper.py` | 先过 §6 清单，不过则不建 |

---

## 2. 5 / 6 / 8 规则（目录直接 `.py` 数）

计数口径与 [package-organization-discipline.md §3.1](package-organization-discipline.md) 相同：计入包目录直接子级 `.py`；**不计** `__init__.py`、`__main__.py`、`tests/`、`conftest.py`。

| 阈值 | 处置 |
|---|---|
| **≤5** | 正常 |
| **6–7** | 预警：PR 须说明为何不能拆 |
| **≥8** | 阻断（legacy 目录见 `scripts/cognitive_directory_anchors.toml` 过渡表） |
| **≥12** | 必须拆分，不接受静默豁免 |

**深度原则：** 宁可多一层浅目录，也不要一层深堆。目标树深 3–4 层，任意节点 ≤5 文件。

---

## 3. 文件体量

| 对象 | 目标 | 硬顶 | 超出处置 |
|---|---|---|---|
| `.py` 文件（含注释） | ≤250 行 | **300 行**（legacy 400） | 拆文件或拆子目录 |
| 类 | ≤120 行 | 150 行 | 提取 collaborator |
| 函数（非 dunder） | ≤30 行 | 40 行 | 提取私有函数 |
| 嵌套深度 | — | 4 | ruff 门禁 |

`plugin.py` 单文件插件包豁免至 500 行，但须单一 `@plugin` 入口。

---

## 4. 命名：路径即语义

### 4.1 禁止冗余前缀

父目录已表达的概念，子文件名**不得重复**：

| 路径 | 禁止 | 应用 |
|---|---|---|
| `session/` | `session_bind.py` | `lifecycle/bind.py` |
| `loop/emit/spine/` | `spine_ep_emit.py` | `ep.py` |
| `infrastructure/session/` | `cognitive_emit.py` | `emit/cognitive.py` |

### 4.2 禁止无语境动词堆叠

下列后缀**仅允许**出现在语义目录下：

| 后缀 | 允许目录示例 |
|---|---|
| `_emit` | `**/emit/**`、`**/fact_emit/**` |
| `_append` | `session/append.py`、`**/append/**` |
| `_commit` | `**/commit/**` |
| `_registry` | `**/registry/**` |

反例（须迁移）：`loop/llm_emit.py` → `loop/emit/cognitive/llm.py`

### 4.3 禁止模糊名

`utils.py`、`helpers.py`、`common.py`、`misc.py`、`shared.py`、`interfaces.py` —— **禁止新增**；存量列入 legacy backlog。

### 4.4 兄弟文件相干性

同目录文件应满足至少一条：

1. 同一概念群的变体（如 `decision_gates/repeat_tool_call.py`）
2. 同一管道的阶段（如 `compile/compiler.py` + `compile/assembler.py`）
3. 同一 Facade 的分解（如 `plugin/manifest.py` + `plugin/context.py`）

若无法用一句话描述「这 N 个文件共同构成什么」，则目录切分错误。

---

## 5. 锚点包布局（ADR-0195 P5+ 示范）

### 5.1 `lca/harness/` 根

```text
harness/
├── flags.py · plan.py          # 根：仅跨子域横切
├── plugin/                     # 插件 Manifest 机制（≤5）
│   ├── context.py · declaration.py · manifest.py · spec_projection.py
│   └── __init__.py             # 公开门面（原 plugin_api）
└── continuous/                 # 持续控制面（≤5）
    ├── session.py · queue.py · serialization.py
```

### 5.2 `lca/cognition/` 根

```text
cognition/
├── perceive/hub.py · service.py
├── brain/gate_service.py · hook_registry.py · …
├── wire/envelope.py · registry_factory.py   # 认知层 transport 适配，非 HTTP
├── body/ · memory/ · sensors/ · collaboration/
```

根目录**仅** `__init__.py`；禁止在根堆 `gate_service.py` 等「待归类」文件。

### 5.3 `lca/loop/`

```text
loop/
├── driver.py · transaction.py · fact_gateway.py · transport.py
├── emit/
│   ├── spine/ep.py · phase_fact.py · kernel_loop.py
│   └── cognitive/llm.py · reasoner.py · agent_spawn.py
└── commit/
    act_journal.py · memory_journal.py · delegation_journal.py
    tool_journal.py · phase_spine.py
```

`FactGateway` 是唯一事实生产门面；`emit/` 与 `commit/` 是机制分解，不是第二入口。

### 5.4 `lca/session/`

```text
session/
├── append.py · catalog.py · fold.py
└── lifecycle/
    bind.py · checkpoint.py · recovery.py · repair.py
```

---

## 6. 新建文件/agent 清单（每次必过）

```text
□ 父目录直接 .py 加本文件后仍 ≤5？
□ 文件名去掉父目录前缀后仍可读？
□ 文件名是名词短语，非动词+emit/append 临时组合？
□ 预计行数 <250？超过则先拆设计
□ 职责与同目录兄弟相干？
□ 映射到 v3 九群或 platform-directory 已有子包？
□ 不是「先放这以后再挪」？（若是，禁止提交）
```

---

## 7. CI 与命令

```bash
# 锚点包严格门禁（合并阻断）
uv run python scripts/check_cognitive_directory.py

# 全库盘点（报告，不阻断 legacy）
uv run python scripts/check_cognitive_directory.py --report-only

# 包规模（默认 cap=5）
uv run python scripts/check_package_size.py
```

锚点列表：`scripts/cognitive_directory_anchors.toml`

架构测试：`tests/architecture/test_cognitive_directory.py`

---

## 8. 迁移态

旧路径保留 COMPAT shim，模板：

```text
# COMPAT(owner: ADR-0195, from: lca.loop.llm_emit,
#       to: lca.loop.emit.cognitive.llm,
#       delete_when: rg 'lca\.loop\.llm_emit' → 0 且 arch test 绿)
```

`delete_when` 必须可机器检测；无 delete_when = 红灯。

---

## 9. 与 ADR-0195 关系

| ADR-0195 P-L5 | 本文 |
|---|---|
| plugin 包 ≤8 .py | 全包 ≤5 .py（更严） |
| 43 顶层 → seam 树 | 每层节点 ≤5，路径可读 |
| 平台 Done #5 | `observability/` 无 >15 文件目录 → 无 >5 文件目录 |

---

## 10. 参考

- [ADR-0195 Platform Convergence](../adr/0195-platform-architecture-convergence.md)
- [ADR-0190 Extreme Plugin Organization](../adr/0190-extreme-plugin-organization.md)
- [package-organization-discipline.md](package-organization-discipline.md)
