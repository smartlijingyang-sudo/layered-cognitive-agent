# ADR-0074 Plugin-Everything 实施追踪

> **这是 ADR-0074「Plugin-Everything 裁剪版」的中央实施账本。所有 superpowers session 进来到工作前先读这一份。不需要读对话历史——本文件自包含。**

## 0. 读取顺序

新 session 的 agent 必须按下列顺序读完前 6 节，再开始动手：

1. §1 状态总览（知道当前 Phase 与 Next Action）
2. §2 5 个 Phase 0 决策（不可变更）
3. §3 依赖图（理解 PR ↔ PR ↔ ADR 阻塞）
4. §4 当前 PR 详情
5. §6 Session 日志（看上一 session 干了什么、留了什么）
6. §7 已知陷阱（避免重复踩坑）

读完上述 6 节后，再去读：

- `/home/lichao/layered-cognitive-agent/AGENTS.md`
- `/home/lichao/layered-cognitive-agent/docs/adr/0074-plugin-everything-trimmed-implementation.md`
- 当前 PR 涉及的具体 ADR 章节

---

## 1. 状态总览

| Phase | PR | 标题 | 状态 | 分支 | Commit | 完成日 | 阻塞 |
|:-:|:-:|---|:-:|---|---|:-:|---|
| **0** | A | v3.1 宪法补丁 | ✅ Done | `feat/adr-0074-phase-0-constitutional-alignment` | `f980ace0` | 2026-08-21 | — |
| **0** | B | ADR-0074 重排 | ✅ Done | `feat/adr-0074-phase-0-constitutional-alignment` | `c8c1b007` | 2026-08-21 | — |
| **0** | D | README 收尾 | ✅ Done | `feat/adr-0074-phase-0-constitutional-alignment` | `5e32e704` | 2026-08-21 | — |
| **1** | 0 | audit 测量网 | ⏳ Ready | `feat/adr-0074-phase-1-pr-0-audit-scripts` | — | — | — |
| **1** | 0.5 | 清 22 个 pre-existing 失败 | ⏳ Ready（与 PR-0 并行） | TBD | — | — | — |
| **1** | 1 | ControlSlot + ControlPlan 数据面 | ⛔ Blocked | — | — | — | PR-0 |
| **1** | 2 | PluginDefinition.control 可选段 | ⛔ Blocked | — | — | — | PR-1 |
| **1** | 2.5 | 11 关系代数扩展 CapabilityPlan | ⛔ Blocked | — | — | — | PR-2 |
| **2** | 3 | CompiledRunPlan + PlanCompiler | ⛔ Blocked | — | — | — | PR-2.5 |
| **2** | 4 | think.guard / stop.decide 原子化 | ⛔ Blocked | — | — | — | PR-3 |
| **2** | 5 | spawn.bind_plan | ⛔ Blocked | — | — | — | PR-3 + ADR-0071 |
| **3** | 6 | plan_ref × Journal 绑定 | ⛔ Blocked | — | — | — | PR-5 |
| **3** | 7 | RunFact / CommandEnvelope 收口 | ⛔ Blocked | — | — | — | PR-6 + ADR-0073 |
| **3** | 8 | ArtifactController（4 状态机） | ⛔ Blocked | — | — | — | PR-7 |
| **4** | 9 | Creator 4 面化 | ⛔ Blocked | — | — | — | PR-8 |
| **4** | 10 | Golden profile + 文档收尾 | ⛔ Blocked | — | — | — | PR-9 |
| **4** | 12 | PlanTemplate + 关系图谱可视化 | ⛔ Blocked | — | — | — | PR-10 |

**Next Action**：PR-0（audit 测量网）。新 session 接进来就干这个。

**累计完成**：3 / 17（含 PR-0.5 + PR-2.5）。

---

## 2. 5 个 Phase 0 决策（不可变更）

> 这些决策在 Phase 0 review 中由用户拍板，后续 session **不得重新决定**。如果发现需要修改，必须先与用户确认。

| # | 决策 | 来源 | 不可变更理由 |
|--:|---|---|---|
| **1** | README 已把 0062 / 0070 / 0072 三者都标 Accepted | Phase 0 PR-D | 三者实现都已合并到 main（`e0eb2484` / `eca3966b` / `26bf0aaf`），仅标 0062 不一致 |
| **2** | PR-3 ↔ PR-4 互换：原 PR-3 → 新 PR-4，原 PR-4 → 新 PR-3 | Phase 0 PR-B | think.guard 迁移依赖 ControlPlan 编译产物；先有 PR-3 才能静态表达 |
| **3** | PR-0.5 新增：22 个 pre-existing 失败从外部风险并入主路径 | Phase 0 PR-B | PR-1 起步即会被这 22 个失败拖累 CI |
| **4** | PR-2.5 拆出：11 关系代数数据面前移到 PR-2 末尾，图谱可视化保留到 PR-12 | Phase 0 PR-B | PR-3 CompiledRunPlan 需要 11 关系才能完整表达 governance |
| **5** | 元 ADR 例外：README header 已声明「元 ADR（如 ADR-0074）是例外」 | Phase 0 PR-D | ADR-0074 同时是接受链记录器，旧规则不适用 |

---

## 3. 依赖图

### 3.1 PR ↔ PR（同一 Phase 0 计划内）

```
PR-0 (audit)
   ↓
PR-0.5 (清失败) ← 可与 PR-0 并行
   ↓
PR-1 (ControlSlot + ControlPlan dataclass)
   ↓
PR-2 (PluginDefinition.control 可选)
   ↓
PR-2.5 (11 关系代数扩展 CapabilityPlan)
   ↓
PR-3 (CompiledRunPlan + PlanCompiler)
   ↓
PR-4 (think.guard / stop.decide 原子化)
   ↓
PR-5 (spawn.bind_plan)
   ↓
PR-6 (plan_ref × Journal)
   ↓
PR-7 (CommandEnvelope 收口)
   ↓
PR-8 (ArtifactController)
   ↓
PR-9 (Creator 4 面化)
   ↓
PR-10 (Golden + 文档收尾)
   ↓
PR-12 (PlanTemplate + 关系图谱)
```

### 3.2 PR ↔ 外部 ADR

| PR | 依赖 ADR | 依赖原因 | 外部 ADR 状态 |
|--:|---|---|---|
| PR-5 | ADR-0071 Composer-per-Cluster | spawn.bind_plan 需要 4 个 sub-composer | Proposed — **必须先落地** |
| PR-7 | ADR-0073 Session Path Convergence | CommandEnvelope 收口需要 SessionService Protocol | Proposed — **必须先落地** |

### 3.3 已落地依赖（无需重做）

| ADR | Commit | 提供什么 |
|---|---|---|
| ADR-0070 Reducer-as-Plugin | `eca3966b` | Reducer Protocol + `_loop` 中间产物收口 |
| ADR-0072 Null-Default Discipline | `26bf0aaf` | NullCritic / NullSynthesizer / NullRetrievalPolicy |
| ADR-0062 Plugin Runtime Cleanup | `e0eb2484` | Cordis Fiber Boot 单轨 + L4 spawn 闭合 |
| ADR-0071 Composer-per-Cluster | TBD | **外部依赖**（见 §3.2） |
| ADR-0073 Session Path Convergence | TBD | **外部依赖**（见 §3.2） |

---

## 4. 当前 PR 详情：PR-0（audit 测量网）

### 4.1 目标

让 reviewer 一行命令看清当前 hardcode 在哪（Control Slot 投稿分布 / State 写入点 / 直接 effect 调用 / 残留 hook 挂载点）。

### 4.2 新增文件

| 文件 | 作用 |
|---|---|
| `lca/harness/diagnostics/audit_control_surface.py` | 扫描 plugin Manifest / Profile，输出每个 Control Slot 的投稿清单 |
| `lca/harness/diagnostics/audit_state_writers.py` | 用 `ast` 扫描 `lca/layer1_cognitive/`、`lca/layer2_runtime/`、`lca/layer3_agent/`，输出 `state.x = ...` 字面位置 |
| `lca/harness/diagnostics/audit_direct_commands.py` | 扫描 Body/SafeExecutor 内直接调用 sandbox/transport 的路径 |
| `lca/harness/diagnostics/audit_hook_attach.py` | 扫描 `hooks.trigger` / `_emit` / `middleware_bag` 残留调用点 |
| `tests/harness/test_audit_control_surface.py` | 4 个对应测试 |
| `tests/harness/test_audit_state_writers.py` | |
| `tests/harness/test_audit_direct_commands.py` | |
| `tests/harness/test_audit_hook_attach.py` | |

修改文件：

- `scripts/lca-ops`：注册 4 个 audit 子命令（参考现有 audit / diagnose 子命令注册方式）

### 4.3 实现要点

- `audit_*.py` 是 **pure-function**：输入路径 → 输出 `dict[str, list[Finding]]`
- 用 `ast` 模块扫描，避免 import 时副作用
- `Finding` dataclass：`path / line / col / kind / message`
- 子命令输出格式：人类可读 + `--json` 给机器用（参考 `lca-ops inspect-tree` 的现有风格）

### 4.4 不变量

- **不改 ADR 文件**（0066/0067/0068/0069/0071/0073/0070/0072/0062 任何文件一字不改）
- **不动 layer 分层**：contracts/ 不能 import 实现层
- **不修 22 个 pre-existing 失败**（那是 PR-0.5 范围）
- **不删除 `_loop` / `_emit` / `middleware_bag`**（PR-0 只观察不修复）
- **不扩张到 PR-1 范围**（不在 PR-0 内顺手做 ControlSlot 枚举或 control 字段）

### 4.5 验证流程

```sh
# 1. ruff check + format
uv run ruff check --fix lca/harness/diagnostics/ scripts/lca-ops tests/harness/test_audit_*.py
uv run ruff format lca/harness/diagnostics/ scripts/lca-ops tests/harness/test_audit_*.py

# 2. 新增的 4 个 audit 测试
uv run pytest --no-cov tests/harness/test_audit_*.py -v

# 3. lca-ops 子命令可调用
uv run python scripts/lca-ops audit control-surface 2>&1 | head -30
uv run python scripts/lca-ops audit state-writers 2>&1 | head -30
uv run python scripts/lca-ops audit direct-commands 2>&1 | head -30
uv run python scripts/lca-ops audit hook-attach 2>&1 | head -30

# 4. 不破坏既有测试
uv run pytest --no-cov tests/harness/ -q
```

### 4.6 完成判据

- 4 个 audit 子命令输出**有内容**（不是空报告），且格式可读
- 4 个测试文件全过
- harness 测试无新增失败（pre-existing 22 个保持原状）
- ruff 无新增警告

### 4.7 提交规范

```text
feat(harness): PR-0 audit scripts — control-surface / state-writers / direct-commands / hook-attach

- 新增 lca/harness/diagnostics/audit_*.py（4 个 pure-function 扫描器）
- 新增 tests/harness/test_audit_*.py（4 个对应测试）
- scripts/lca-ops 注册 audit 子命令
- ADR-0074 PR-0 落地

Refs: ADR-0074 phase 1 / PR-0
```

### 4.8 完成后如何更新本追踪

1. 在 `git commit` 后 commit hash
2. 更新 §1 状态总览：PR-0 行 → ✅ Done
3. 在 §6 Session 日志 追加本次 session 记录
4. 如果发现新陷阱，追加到 §7
5. 如果发现 PR 详情需调整（实现中发现 spec 偏差），更新 §4 但**保留变更说明**
6. commit 追踪文件更新（与代码 commit 分开，避免一个 commit 含两类变更）

---

## 5. 已完成 Phase 详情

### Phase 0：宪法对齐与顺序重排（2026-08-21）

**Goal**：在不破坏 v3 宪法的前提下，让 ADR-0074 的 PR 序列在宪法层面对齐、可被下游 agent 无歧义执行。

**Commits**（全部在 `feat/adr-0074-phase-0-constitutional-alignment` 分支）：

| Commit | 内容 | 文件 |
|---|---|---|
| `f980ace0` | v3.1 宪法补丁（§1 双层分类 + §2 C1 闭集细化 + CV1-CV6 验收） | `docs/design/2026-08-21-cognitive-primitive-constitution-v3-1.md`（+156） |
| `c8c1b007` | ADR-0074 重排（PR 顺序 + V9 评分 + Boot 失实修正 + 兼容性表） | `docs/adr/0074-plugin-everything-trimmed-implementation.md`（+371） |
| `5e32e704` | README 收尾（0062/0070/0072 Accepted + 元 ADR 例外） | `docs/adr/README.md`（±32） |

**Phase 0 总评审**：8/10（评估报告见对话历史；落地后无后续修订）。

**Phase 0 留下的关键约束**（详见 §2 决策表）。

---

## 6. Session 日志

> 每个 superpowers session 完成后追加一条。格式：session 号 + 日期 + 完成项 + 留下的状态。

### Session 1（2026-08-21）：Phase 0 落地 + 评估

- **完成**：Phase 0 三个 PR（v3.1 补丁 + 0074 重排 + README 收尾）
- **评估报告**：8/10 架构优雅度
- **决策**：5 个 Phase 0 决策拍板
- **遗留**：分支未合并到 main；等待用户 review
- **下一步**：用户决定是否合并；合并后启动 Session 2 做 PR-0

### Session 2（TBD）：Phase 1 PR-0

[待填]

---

## 7. 已知陷阱（living document）

> 任何 session 遇到的新陷阱、ADR 漂移、测试 flaky、依赖变更，都追加到这里。后续 session 进来到必读。

### 7.1 已记录

- **`docs/adr/README.md` 字数预算 900**：每加一行 ADR 表要重算；em-dash (`——`) 与单 em-dash (`—`) 等价（都算 1 word）；markdown 表格里多行描述挤预算。**经验**：所有 ADR 描述保持短，主标题句即可，详细描述去 ADR 文件。
- **`docs/adr/README.md` 测试强制**：`tests/test_refactor_guards.py::test_adr_index_matches_filesystem` 要求 README 列出所有 `docs/adr/*.md` 文件。**不能删除 ADR 文件来减字数**——会破测试。
- **ADR 状态变更路径**：ADR 文件本身**不能改**（"不改旧文件" 规则），状态变更通过：
  - README 索引更新（可）
  - 新 ADR 的 `Refines` / `Supersedes` 关系（可）
  - 用户单独接受动作（用户决定）
- **ADR-0070 与 Boot 双轨无关**：ADR-0070（`eca3966b`）只收口 `_loop` 中间产物；Boot 双轨由 ADR-0062 PR-3/PR-4（`e0eb2484`）处理。**新 agent 不要再混淆**。
- **22 个 pre-existing 测试失败**：来源是 journal v2 envelope 错配 + DSH 删除遗留 + plugin context boot 三类。**不在 PR-0 范围内修复**；PR-0.5 处理。
- **`lca-ops` 子命令注册机制**：参考 `scripts/lca-ops` 现有 audit/diagnose 子命令。新增 audit 子命令时复用相同模式。

### 7.2 待识别

[新 session 发现时追加]

---

## 8. 文件索引

| 文件 | 用途 |
|---|---|
| `/home/lichao/layered-cognitive-agent/AGENTS.md` | 工作区纪律（最严格） |
| `/home/lichao/layered-cognitive-agent/docs/adr/0074-plugin-everything-trimmed-implementation.md` | **必读** PR 表 + 兼容性 + 风险 |
| `/home/lichao/layered-cognitive-agent/docs/design/2026-08-21-cognitive-primitive-constitution-v3-1.md` | v3.1 补丁 |
| `/home/lichao/layered-cognitive-agent/docs/design/2026-08-21-code-aligned-architecture-audit.md` | 审计原文（理解为什么） |
| `/home/lichao/layered-cognitive-agent/docs/design/2026-08-19-cognitive-primitive-constitution-v3.md` | v3 宪法（非变动基线） |
| `/home/lichao/layered-cognitive-agent/docs/adr/0066-declarative-atomic-control-plugins.md` | Control Slot 9 槽位来源 |
| `/home/lichao/layered-cognitive-agent/docs/adr/0068-compiled-plugin-kernel-and-unified-run-plan.md` | CompiledRunPlan 三件套来源 |
| `/home/lichao/layered-cognitive-agent/docs/adr/0069-agent-primitive-system-and-declarative-grammar.md` | 13 群分类学 + 11 关系来源 |
| `/home/lichao/layered-cognitive-agent/docs/adr/0071-composer-per-cluster.md` | PR-5 外部依赖 |
| `/home/lichao/layered-cognitive-agent/docs/adr/0073-runsession-sole-session-path.md` | PR-7 外部依赖 |

---

## 9. 变更记录（本追踪文件本身的修订）

| 日期 | 修订 | 修订人 |
|---|---|---|
| 2026-08-21 | 初版：状态总览 + 5 决策 + PR-0 详情 + Phase 0 完成 + Session 1 日志 | Session 1 agent |
| TBD | PR-0 完成后追加 | Session 2 agent |