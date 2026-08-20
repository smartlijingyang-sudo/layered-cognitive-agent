# LCA Documentation Standard

本文定义 LCA 文档的层级分类、写作规范、字数预算和验证门禁。

## 层级分类法：每个事实一个家

| 层级 | 职责 | 位置 | 不属于这里 |
|---|---|---|---|
| 根 AGENTS.md | 常驻命令：每个会话都需要的规则，每条 1-3 行，链接到具体家 | `AGENTS.md` | 故事、示例、situational procedures |
| 架构地图 | 有序地图：组合、核心包、循环、接缝、扩展点；改代码前必读 | `docs/architecture.md` | 类型定义（→ specs）、每包细节（→ README）、决策理由（→ ADR） |
| ADR | 已采纳的架构决策：为什么、放弃了什么、必须验证什么 | `docs/adr/` | 迁移计划、验收清单、fixture 演练、已上线后的 spec-speak |
| 现行规范 | 当前有效的规格说明和操作文档 | `docs/specs/` | 历史设计理由（→ design）、实现状态标注 |
| 设计文档 | 详细设计：类型、语义、API | `docs/design/` | 行为叙述（→ architecture.md）、每包细节（→ README） |
| 实现计划 | 分阶段实施计划（已完成或进行中） | `docs/plans/` | 决策理由（→ ADR）、已上线后的验收清单 |
| 交付状态 | 阶段交付报告 | `docs/status/` | — |
| Cookbook | 编号步骤的操作指南 | `docs/cookbook/` | 设计理由（→ ADR） |
| 术语表 | 术语定义 + 代码双向守护 | `docs/specs/glossary.md` | — |

**归位规则**：bug → postmortem（暂无）；决策理由 → ADR；操作步骤 → cookbook；类型定义 → design；包契约 → README；常驻命令 → 根 AGENTS.md。

## 写作规范

### 基础原则

- **写当前状态，不写变更历史**。避免「之前 / 现在 / 不再」「PR / commit / stack 位置」；命名活的机制。变更故事放 commit、PR、ADR；后两者可引已合并 PR 作为证据。
- **每个非平凡改动至少更新一个 ADR**。更新拥有该决策的 ADR 或新增；只有纯机械/局部编辑豁免。
- **一行一段**（`verify_md_wrap`）：用编辑器软换行。代码块、表格、列表结构保持格式。
- **注释和 docstring 写完整契约，不写推理过程**。保留行为、失败、时序、所有权、模态、异常、后果、非显然方向；删除叙述、测试演练、评审分析、代码复述。保留局部契约并链接其理由。
- **直接写：命名行动者和事实**。保留 `seam` 给定义好的能力。命名确切的检查、类型、API、操作或行为，而非隐喻性的「gate / vocabulary / surface」。
- **交叉引用用机器可检查的相对路径**，不用裸文件名或 ADR 编号。`verify_md_links` 拒绝缺失目标和死 `#fragment`。

### 文档结构

一个文档的主题和树位置决定其范围：描述自己的主题到适当细节，只按目的、职责和高层行为描述直接子节点；链接到拥有后代以获取更低层细节。文档类型不扩大该范围。

- **tutorial**（教程）：按顺序路径到结果，只引入每步所需。先私有分类读者的起始知识和每个概念为 beginner/intermediate/advanced。在依赖概念前建立先决条件，逐步增加难度，把不必要的 advanced 材料移到后续 tutorial 或 reference。
- **reference**（参考）：定义查找范围和当前行为，没有教学顺序。

 substantial tutorial 和 reference 内容分开；任一部分小时标注一节。

###  slop 检查清单

任何文档中猎杀这些：

- 同一规则在多个家重复。grep 特征短语；保留一个家，其余链接。
- 叙述历史或战争故事：「之前」「现在」「不再」「曾经」「重命名」「被移动到」、PR、commit。陈述当前事实；需要时链接 ADR 或 postmortem。
- 散文或图中的实现状态标注（「已实现！」「未来：…」）。状态会腐烂；仓库布局和包清单携带它。
- 手动复述目录、docstring 或测试/包/状态清单，而源码或生成器是权威的。
- 推理过程：一步一步实现叙述、显然分支的证明、测试演练、或拒绝的局部替代方案。保留结果契约或持久理由；删除用于推导它的路径。
- 相邻方法旁重复的理由，而非在拥有的能力或 helper 处一次。
- 段落墙：一个段落承载多条规则和括号旁白。拆分或将细节降级到其家。
- 强调通胀：到处 bold、CAPS、「关键」意味着没有突出。保留强调给改变行为的从句。
- `implemented/` ADR 中的 spec-speak：「应该」、迁移计划、验收清单。已采纳的 ADR 描述的是什么，而非应该是什么。

## 字数预算

`scripts/doc_budgets.json` 设置常驻文档上限；`uv run python scripts/verify_doc_budgets.py` 拒绝超限或缺失文件。

当门禁变红时：

1. **迁移**属于另一层级的内容；需要时留一行链接。
2. **压缩**属于这里但可以更短的内容。
3. **提高**上限仅当文字需要空间时；在 PR 中证明 manifest diff。太低的上限是预算 bug。

上限是护栏，不是缩减目标。在目标或以下，保留至少 5% 余量；在目标以上，冻结上限直到迁移或压缩使文档降到目标以下。仅当文档仍有空间时降低上限，当内容否则会被删除时提高上限。

目标：
- 根 `AGENTS.md` ≤ 2000 字
- `docs/architecture.md` ≤ 2000 字
- `docs/adr/README.md` ≤ 800 字
- `docs/specs/glossary.md` ≤ 3000 字（术语表例外）
- `docs/specs/run-live.md` ≤ 4000 字（操作文档例外）
- `docs/specs/harness-spine-spec.md` ≤ 5000 字（执行规约例外）

## 验证门禁

| 脚本 | 强制 |
|---|---|
| `scripts/verify_md_links.py` | Markdown 相对链接必须解析（目标文件存在 + `#fragment` 指向真实标题） |
| `scripts/verify_doc_budgets.py` | 字数预算超限拒绝 |
| `scripts/verify_md_wrap.py`（TODO） | 一行一段（软换行） |

这些脚本是 `pre-commit` 的一部分，但不阻塞发布。CI 运行全部门禁。

## ADR 生命周期

每个 ADR 有路径编码的生命周期：

- **Accepted** — 已采纳的决策。文件记录决定了什么和放弃了什么，并**保持与实际上线的东西一致**：当代码后来移动文件、重命名包、或改变键/默认值时，ADR 在同一改动中更新以匹配（仅事实 — 路径、名称、结构 — 而非决策本身）。
- **Superseded** — 被新 ADR 取代。保留原 ADR 但标注 `Status: Superseded` 并链接新 ADR。
- **Deprecated** — 不再适用但未被明确取代。标注 `Status: Deprecated` 和原因。

ADR 格式：

```markdown
# ADR-XXXX: 标题

## 状态
Accepted | Superseded by ADR-YYYY | Deprecated

## 背景
动机，独立于解决方案写。

## 决策
决定了什么，放弃了什么。

## 后果
上线了什么，验证了什么。

## 替代方案
考虑过但拒绝的方案，每个一行理由。
```

## 维护规则

- 推翻已有决定时，新建一篇 ADR 标记 `Supersedes: ADR-XXXX`，不改旧文件。
- 这些文档的价值在于记录某一时刻的判断，不在于时刻反映最新状态。
- 当 shipped note 不太可能指导未来工作时，考虑标记 Deprecated 而非继续维护。
- CI `scripts/verify_md_links.py` 断言所有相对链接解析。
