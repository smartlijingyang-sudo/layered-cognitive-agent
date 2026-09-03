# Agent Note Template — 四生命周期合并骨架

本文件是**唯一**的 note 模板。复制本文件的对应段落到 `proposed/<class>/YYYY-MM-DD-<topic>.md` / `implemented/<class>/...` / `rejected/<class>/...` / `archived/<class>/...`,然后填入 `<...>` 占位符。

> **共同约束**(各 lifecycle 都生效,见根 [`README.md`](../README.md) 与各子目录 `AGENTS.md`):
>
> - 文件名:`YYYY-MM-DD-<topic>.md`,首次提出日期为准。
> - Header 三行硬约束:标题、`Status:` 行(值必须与目录一致)、空行。
> - Body 必须从 `## Problem` 开头,动机描述,不含解。
> - `## Alternatives considered` 强制;没有 Alternatives = 没记录"为何不 Y"。
> - 跨 note 引用一律相对 markdown 链接,不用裸编号。
> - `.zh.md` 当前**不预生成**;真要翻译时复制 `.md` 后逐节对齐,i18n.yaml 同步登记。

---

## 1. proposed/ —— 未实施决策

适用目录:`docs/notes/proposed/<class>/YYYY-MM-DD-<topic>.md`(`class` ∈ {`contract`, `primitive`, `seam`, `profile`, `runbook`, `postmortem`})。

```markdown
# Agent Note: <title>

Status: proposed

## Problem

<动机陈述,不含解;说明现在缺什么 / 错什么 / 阻挡什么。可 2-4 段。>

## Proposal

<准备实施的改动;**将来时**;清晰说明改动的边界、影响的 ADR / Protocol / Profile / seam。>

## <可选:技术细节节,例如 `## Wire contract` / `## Topology` / `## Schema`>

<本提案特有的技术信息;若没有可整节省略。>

## Alternatives considered

### Why not <X>?

<被否决方案 X 的动机,以及为何在本场景下不及 Y。>

### Why not <Z>?

<被否决方案 Z 的动机,...>。

## Acceptance criteria

<可观察的状态;不是 checklist。例如:"`<seam>` 的 `Provider` 注册条目数从 N 降到 N +1,且 `why-plugin <id>` 显示 capability 归属正确"。>

## Risks

<会出什么问题、放弃什么、什么时候撤回。>

## <可选:`## Open questions` / `## Migration plan` / `## Related`>

<跃迁到 `implemented/` 前需要先答清楚的事项;迁移分步;外部链接。>
```

跃迁到 `implemented/` 时,把 `## Proposal` 改写为现在时的 `## Decision`;`## Acceptance criteria` / `## Risks` 折叠为 `## Consequences` 或保留为 `## Verification` / `## Testing`(详见 [`implemented/AGENTS.md`](../implemented/AGENTS.md))。

---

## 2. implemented/ —— 已落地决策

适用目录:`docs/notes/implemented/<class>/YYYY-MM-DD-<topic>.md`。**正文用现在时**,描述现状而非计划。

```markdown
# Agent Note: <title>

Status: implemented

## Problem

<动机陈述(同 proposed 段;若由 proposed 跃迁而来,保留原 Problem 即可)。>

## Decision

<现状是什么;**现在时**;指出路径、符号、默认值、机制归属。写"`<module>` 拥有 X,`<seam>` 通过 `<provider>` 实现",而不是"我们将..."。>

## <可选:技术细节节>

<若提案时已有 `## Wire contract` 等节,跃迁后**重写**为现状;不要保留 proposal 时的规划性段落。>

## Alternatives considered

<保留 proposed 时的否决理由;若自跃迁后否决场景变了,补充"新增否决 Y"段落,但不删原段落。>

## Consequences

<trade-off 放弃了什么、获得了什么;可包含"`Profile X` 因此不能再作为 `<capability>` 的唯一入口"等负面副作用。>

## <可选:`## Testing` / `## Verification` / `## Related`>

<描述**当前**哪些测试 / 门禁 / 文档 pin 住了这个决策;**不**写"未来还要加的测试"。>
```

实施同 PR 内:`Status: proposed` → `Status: implemented`;`## Proposal` → `## Decision`;`## Acceptance criteria` / `## Risks` → `## Consequences` 或 `## Verification` / `## Testing`。

---

## 3. rejected/ —— 未通过的提案

适用目录:`docs/notes/rejected/<class>/YYYY-MM-DD-<topic>.md`。判决理由写在 `Status:` 行尾部一行;**正文不再改动**(若由 proposed 跃迁则沿用当时的版本)。

```markdown
# Agent Note: <title>

Status: rejected — <one-line verdict,见根 README §3.1>

## Problem

<动机陈述(同 proposed 段;沿用).>

## Proposal

<原 proposed 时的方案;**冻结**,不改。>

## <可选:技术细节节>

<同 proposed。冻结。>

## Alternatives considered

<否决理由必须在 Alternatives considered 里**显式**指出本提案为何被 `<X>` 击败,而不是藏在 verdict 一行话里。>

## <可选:`## Acceptance criteria` / `## Risks` / `## Open questions`>

<原 proposed 时的节;冻结。>
```

verdict 行写法:

- ✅ `Status: rejected — 与 ADR-0042 的 `<seam>` 边界冲突,Profile 拓扑无法嵌入。`
- ✅ `Status: rejected — 被同 PR 的 `<new-note-id>` 在 Alternatives considered 中完整覆盖,见其 `### Why not <X>?`。`
- ❌ `Status: rejected — 暂时不做。`(措辞留口子,该删)
- ❌ `Status: rejected — 优先级低,后续再看。`(同上)

判定不满足"还能劝退未来人" → 删除整组三元组,见 [`rejected/AGENTS.md`](../rejected/AGENTS.md)。

---

## 4. archived/ —— 冻结的历史记录

适用目录:`docs/notes/archived/<class>/YYYY-MM-DD-<topic>.md`。**Status 行保持** `Status: implemented` 不变,`Archived:` 行紧贴其下方;正文冻结。

```markdown
# Agent Note: <title>

Status: implemented
Archived: <YYYY-MM-DD,归档当日>

## Problem

<冻结前 implemented/ 当时的 Problem;不改。>

## Decision

<冻结前 implemented/ 当时的 Decision;不改。>

## <可选:技术细节节>

<冻结前原状;不改。>

## Alternatives considered

<冻结前原状;不改。>

## Consequences

<冻结前原状;不改。>

## <可选:`## Testing` / `## Verification` / `## Related`>

<冻结前原状;不改。>
```

归档动作的**唯一**允许集合见 [`archived/AGENTS.md`](../archived/AGENTS.md);除此之外任何字符级修改(包括"修一个错别字")均禁止。

---

## 5. 复制与跃迁 checklist(总览)

| 步骤 | 动作 | 见 |
|---|---|---|
| 1 | 复制本文件对应 lifecycle 段到目标路径 | 本文件 §1–§4 |
| 2 | 替换所有 `<...>` 占位符 | — |
| 3 | 若写 `## Alternatives considered`,每个否决方案一段 | 根 README §3.3 |
| 4 | 提交 PR;同 PR 内若要跃迁,执行跃迁 checklist | 各 lifecycle AGENTS.md |
| 5 | 若最终归档:执行归档五项硬约束 | `archived/AGENTS.md` |