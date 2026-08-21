# LCA Documentation Standard

本文定义 LCA 文档的层级分类、写作规范和防膨胀规则。

## 层级分类法：每个事实一个家

| 层级 | 职责 | 位置 | 不属于这里 |
|---|---|---|---|
| 根 AGENTS.md | 常驻命令：每个会话都需要的规则，每条 1-3 行，链接到具体家 | `AGENTS.md` | 故事、示例、过程性文档 |
| ADR | 已采纳的架构决策：为什么、放弃了什么、必须验证什么 | `docs/adr/` | 迁移计划、验收清单、实现状态 |
| 现行规范 | 当前有效的规格说明和操作文档 | `docs/specs/` | 历史设计理由（→ ADR）、实现状态标注 |
| 权威设计 | 认知原语宪法——唯一允许长期驻留的设计文档 | `docs/design/` | 一次性分析、迁移设计、评估草案 |
| 观测子系统 | ADR-0065 的可观测性子系统详细规格 | `docs/observability/` | 通用架构叙述（→ ADR） |
| 术语表 | 术语定义 + 代码双向守护 | `docs/specs/glossary.md` | — |

**归位规则**：决策理由 → ADR；操作步骤 → 规范或 ADR 后果；类型定义 → 规范；常驻命令 → 根 AGENTS.md。**不允许**新建 `plans/`、`research/`、`status/` 目录——已完成的工作活在代码和 ADR 里。

## 写作规范

- **写当前状态，不写变更历史**。避免「之前 / 现在 / 不再」「PR / commit」；命名活的机制。变更故事放 commit message 或 ADR 背景。
- **一行一段**：用编辑器软换行。代码块、表格、列表结构保持格式。
- **注释和 docstring 写完整契约，不写推理过程**。保留行为、失败、时序、所有权、异常、后果；删除叙述、测试演练、代码复述。
- **直接写：命名行动者和事实**。命名确切的检查、类型、API、操作或行为，而非隐喻性的「gate / vocabulary / surface」。
- **交叉引用用相对路径**，不用裸文件名。`verify_md_links` 拒绝缺失目标和死锚点。
- **每个非平凡改动至少更新一个 ADR**。更新拥有该决策的 ADR 或新增。

### slop 检查清单

- 同一规则在多个家重复。grep 特征短语；保留一个家，其余链接。
- 叙述历史：「之前」「现在」「不再」「曾经」「重命名」「被移动到」。陈述当前事实；需要时链接 ADR。
- 实现状态标注（「已实现！」「未来：…」）。状态会腐烂；仓库布局携带它。
- 推理过程：一步一步实现叙述、显然分支的证明。保留结果契约；删除推导路径。
- 段落墙：一个段落承载多条规则。拆分或降级到对应家。
- 强调通胀：到处 bold 意味着没有突出。

## 字数预算

`scripts/doc_budgets.json` 设置上限；`uv run python scripts/verify_doc_budgets.py` 拒绝超限。

当门禁变红时：1) **迁移**属于另一层级的内容；2) **压缩**属于这里但可以更短的内容；3) **提高**上限仅当文字确实需要空间——在 PR 中证明。

目标：
- 根 `AGENTS.md` ≤ 2000 字
- `docs/AGENTS.md` ≤ 1200 字
- `docs/adr/README.md` ≤ 900 字
- `docs/specs/glossary.md` ≤ 3000 字（术语表例外）
- `docs/specs/run-live.md` ≤ 4000 字（操作文档例外）
- `docs/specs/harness-spine-spec.md` ≤ 10000 字（执行规约例外）

## ADR 生命周期

- **Accepted** — 已采纳。**保持与实际上线的东西一致**：代码变更时同一改动更新 ADR 事实（路径、名称、结构），不改决策本身。
- **Superseded** — 被新 ADR 取代。标注 `Status: Superseded` 并链接新 ADR。
- **Deprecated** — 不再适用。标注 `Status: Deprecated` 和原因。
- **当 shipped ADR 不太可能指导未来工作时，标记 Deprecated 而非继续维护。**

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

## 防膨胀规则

- **不允许**新建 `docs/plans/`、`docs/research/`、`docs/status/` 目录。实施计划、研究笔记、交付状态是过程性产物，完成即归档到 git history。
- **`docs/design/` 只接受权威设计**（认知原语宪法级别）。一次性分析、迁移设计、评估草案不入库——结论写入 ADR 或代码。
- **新增 ADR 前问**：这个决策是否已经体现在代码结构里？如果是，不需要 ADR。只有「为什么」不显然的决策才需要 ADR。
- **新增文档前问**：这个事实能否放进已有文档？只有无法归入现有层级的信息才值得新文件。
- 推翻已有决定时，新建 ADR 标记 `Supersedes: ADR-XXXX`，不改旧文件。

## 验证门禁

| 脚本 | 强制 |
|---|---|
| `scripts/verify_md_links.py` | Markdown 相对链接必须解析 |
| `scripts/verify_doc_budgets.py` | 字数预算超限拒绝 |
