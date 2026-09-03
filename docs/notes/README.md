# Agent Notes

English | [中文](README.zh.md)

**新决策**的归宿,不是替代。`docs/adr/` 继续管"跨 ADR 影响架构边界的元决策",Agent Note 管"单点契约 / 原语 / Seam / Profile / 运行手册 / 复盘"。

> **强约束(本目录生效的全部规则)**:
> - **老 ADR 全部不动**(不补状态、不迁移、不重编号、不加 sidecar、不进 archived)。
> - **新决策**(本 README 发布之后)按本文规则走。
> - **任何"瘦身 / 合并 / 替代"动作视为范围外**;若需要,另开 ADR 走原流程。

## 1. 与 `docs/adr/` 的分工

| 关注点 | `docs/adr/`(现行,**不动**) | `docs/notes/`(新增,**新规则生效**) |
|---|---|---|
| 决定粒度 | 跨 ADR、影响架构边界的元决策 | 单点契约 / 原语 / Seam / Profile / 运行手册 / 复盘 |
| 编号 | `0001-…`,顺序编号 | `YYYY-MM-DD-<topic>.md`,首次提出日期 |
| 状态 | `## 状态` Accepted/Proposed/Superseded + 行内 supersede 链 | 闭集三态:`proposed` / `implemented` / `rejected`;`archived/` 是冻结终态 |
| 双语 | 少量 ADR 有 `.zh.md` | **暂不强制** sidecar(等第一条真正需要时再加),不预生成 |
| 修改 | 现有 ADR 自由更新 | `proposed/implemented/rejected` 可改;`archived/` 一旦冻结永久不可动 |

**判定路径**:新决策先问一句"它**会改变其他 ADR 的边界**吗?"。是 → 走 `docs/adr/`(按现有 ADR 流程)。否 → 走 `docs/notes/`。

## 2. 生命周期与目录布局

每条 Agent Note 的物理路径编码两个轴:`{lifecycle}/{class}/YYYY-MM-DD-<topic>.md`。

### 2.1 Lifecycle 与顶层辅助目录(四态 + 两个非 Note 目录)

- **`proposed/`** —— 决策已提出但未实施;实施开始后迁到 `implemented/`。
- **`implemented/`** —— 决策已落地;文件描述**现在的真实状态**(现在时,禁 spec-speak)。
- **`rejected/`** —— 决策考虑过但未通过;**只保留"还能劝退未来人"的提案**,否则删除三元组。
- **`archived/`** —— 实施后被认为不再有指导价值的历史决策;**一旦进入即冻结**,不得修改、移动、翻译、重排。

**非 Note 顶层目录**(不在生命周期路径中):

- **`templates/`** —— Agent Note 模板与可复用段落(由 [docs/notes/templates/note-template.md](templates/note-template.md) 等组成)。不是 note 本身,不被 `check_notes_tree.py` 当 note 校验。
- **`plans/`** —— Agent Note 体系的实施计划/设计稿(本会话前例:[plans/2026-09-03-agents-md-rewrite.md](plans/2026-09-03-agents-md-rewrite.md))。可携带 `## Problem / ## Proposal / ## Acceptance criteria` 段,但**不**走 note lifecycle;不被 `check_notes_tree.py` 当 note 校验。
- **`audit-YYYY-MM-DD.md`**(顶层单文件)—— 由 `scripts/audit_adr_health.py` 或 `lca-audit-notes` 产出的诊断报告,放在 `docs/notes/` 根目录。文件名 `audit-YYYY-MM-DD.md`;内容是只读参考材料,**不参与** Note 校验。

状态值是闭集:`proposed | implemented | rejected`(`archived` 是路径级状态,不参与 `Status:` 字段)。

### 2.2 Class(嵌套,闭集)

闭集初值(代码常量维护,扩展需同时改本表 + `scripts/check_notes_tree.py`,**未启用**):

| Class | 承接范围 |
|---|---|
| `contract` | Protocol、枚举、ID、模型、wire 字段(单点契约) |
| `primitive` | 认知 / Body / Phase 原语;非跨 ADR 但影响闭集 |
| `seam` | 一条 Seam(llm / tools / sandbox / state_store / memory ...)的边界决定 |
| `profile` | Profile YAML 的拓扑与启动契约 |
| `runbook` | 跨 seam / 跨 Profile 的运行模式决策(与 `docs/debug/run-debug-guide.md` 互补) |
| `postmortem` | Incident 复盘;链接 `docs/design/` 中的事后分析与 RCA,不复制内容 |

## 3. 文件格式

### 3.1 Header(三行硬约束)

```markdown
# Agent Note: <title>

Status: <proposed|implemented|rejected>
```

`Status:` 值必须与物理路径一致。rejected 可携带一行原因:

```markdown
Status: rejected — <one-line reason>
```

### 3.2 Body 骨架

每条 note 必须从 `## Problem` 开头(动机,**不含实现词**)。后续章节因 lifecycle 而异:

- **`proposed/`** —— `## Proposal` / `## Alternatives considered` / `## Acceptance criteria` / `## Risks`
- **`implemented/`** —— `## Decision`(现在时) / `## Alternatives considered` / `## Consequences`
- **`rejected/`** —— `## Proposal` / `## Alternatives considered`(verdict 在 `Status:` 行)
- **`archived/`** —— 沿冻结前格式,加一行 `Archived: YYYY-MM-DD`

### 3.3 Alternatives considered(强制)

每条必须有 `## Alternatives considered`:每个被否决方案一段 bold-led 段落或一个 `### Why not <X>?` 子节。**没有 Alternatives = 没记录"为何不 Y",等于邀请重复提案**。

### 3.5 调用入口

**Agent 优先用 CLI**:`./scripts/lca-ops notes-check` / `notes-audit` / `notes-slop` / `notes-list --json` —— 内部调 `scripts/check_notes_tree.py` 等。直接调裸脚本仅供 CI / ad-hoc 调试。

## 4. 何时该写一条

满足任一即写:

- 改变 Protocol / 枚举 / ID / wire 字段(单点契约) → `contract`
- 引入新的认知 / Body / Phase 原语,影响闭集 → `primitive`
- 决定一条 Seam 的边界或 Provider 选择 → `seam`
- 改变 Profile 拓扑或启动契约 → `profile`
- 决定跨 seam 的运行模式 → `runbook`
- Incident 复盘需保留决策与影响 → `postmortem`

**不写**:纯实现细节、临时修复、只换实现不换契约、一次性 UI 文案 —— 归 git commit + 测试。

## 5. 与 `deepseek-harness`(参考)的差异

我们**借鉴**:三态生命周期、path-encoded class、强制 Alternatives、archived 冻结、`## Problem` 开头。

我们**沿用 LCA 自己的**:`docs/adr/`(元决策 + 编号体系 + 中文 README),不强迁移;**老 ADR 一律不动**。

我们**暂不做**:中英 sidecar 全量补齐(本目录新决策按需补即可,不预生成);archived manifest 哈希 append-only(等首条 archived 出现再启用 `verify_notes_archived.py`);`check_notes_tree.py` 自动门禁(步骤一不启用)。

## 6. 本批次交付(步骤一)

只新增下列文件,**未启用任何强制门禁**,不动现有 ADR:

- `docs/notes/README.md`(本文)
- `docs/notes/proposed/AGENTS.md` —— proposed/ 子目录的本地指令
- `scripts/audit_adr_health.py`(via `lca-ops notes-audit`) —— 只读体检,扫描 `docs/adr/`,**不修改任何 ADR**
- `docs/notes/audit-2026-09-03.md` —— 由脚本生成的体检报告(诊断,非迁移计划)
- 根 `AGENTS.md` 一行指针(其余不动)

## 7. 删除条件

本目录在以下条件下整体回退,不留并行 schema:

- 一段时间内没有新决策走 Notes → 保留目录作为"可用入口",不强制启用
- Notes 与 ADR 边界长期模糊 → 二选一,留一个
- archived 一旦启用就**只增不删**(append-only manifest 强制)
