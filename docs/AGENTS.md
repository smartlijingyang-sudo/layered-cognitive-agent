# Documentation Standard

本文定义 LCA 文档的 tier 归属、写作要求和预算门禁。目录导航见 [documentation map](specs/documentation-map.md);根级约束见 [根 AGENTS.md §8](../AGENTS.md)。

## Tier 归属:一个事实只在一个家

| Tier | 职责 | 不承载 |
|---|---|---|
| 根 [`AGENTS.md`](../AGENTS.md) | 每个开发会话都需遵守的高频规则、入口链接、命令、验证矩阵 | 过程记录、方案草稿、实施报告 |
| `docs/adr/` | 已采纳、替代或废弃的架构决策 | 任务分解、验收过程、会议记录 |
| `docs/specs/` | 当前有效的协议、操作指南、术语、目录地图和参考 | 历史理由、一次性调查、外部分析 |
| `docs/design/` | 宪法级或长期有效的设计说明(命名宪法、认知原语、阶段图设计) | 实施状态、复盘报告 |
| `docs/observability/` | Journal、Trace、Metrics、Projection、CLI 的现行规格 | 通用架构叙述 |
| `docs/architecture/` | 检查脚本索引、迭代记录、群映射、门禁矩阵等跨子系统参考 | 单一子系统契约 |
| `history/YYYY-MM/<topic>/` | 已结束的计划、研究笔记、执行记录、审计和交付报告 | 当前规范或仍有效的决策 |
| `roles/`、`skills/`、`deploy/`、`lca/<pkg>/` | 所属组件的就近说明、模板或操作文档 | 跨组件架构决策 |

**归位原则**:决策理由归 ADR;当前契约和操作步骤归 `docs/specs/` 或 `docs/observability/`;已结束工作的过程材料归 `history/`;代码就近说明保留在所属组件目录;一次性外部分析(由第三方或对历史代码的总结)不得进入 `docs/specs/`,应迁到 `history/` 并在归档处标注溯源;被本仓库采纳维护的第三方分析可以留在 `docs/specs/`,但必须在文件头部加 banner 标注作者与维护者。

## 命名与链接

新文档使用小写 kebab-case 文件名;日期敏感的历史材料以 `YYYY-MM-DD-` 开头,或收纳于 `history/YYYY-MM/<topic>/`。历史目录使用 `README.md` 说明范围和索引。文档链接使用相对路径,禁止裸文件名和固定 commit 的 `blob/<sha>` 链接。

`docs/` 根目录只允许 `AGENTS.md`。不得重新创建 `docs/plans/`、`docs/research/`、`docs/status/` 或 `docs/reports/`;这些材料若需保留,应进入 `history/`。新增 ADR 前先判断决定是否已由现有结构表达;新增文档前先判断事实是否能归入既有文档。

## 写作要求

写当前事实和可验证的契约,不写变更叙事。类型、失败语义、时序、所有权和外部后果应明确;实现演练、重复解释、过期状态和无期限 TODO 应删除或归档。交叉引用链接到唯一权威文档,不复制同一规则。JSDoc/行内注释同等约束:陈述完整契约和上下文,不写推理 transcript 或测试旁白。

**Slop checklist**(提交前自检):

1. 同一规则在多个 tier 重述 → 留一个家,其余改链接。
2. 叙事化历史("previously / now / no longer / renamed / PR #123 之后")→ 写当前事实,需要溯源时链接 ADR 或 postmortem。
3. 实现状态注释("implemented! / TODO / 即将 …")→ 状态会腐化,代码与包 manifest 是事实源。
4. 手工罗列的 catalog、JSDoc、测试清单与源代码或生成器重复 → 删,指向生成源。
5. 推理 transcript(逐步实现讲解、明显分支证明、rejected alternatives)→ 留结论与契约,删推导过程。
6. 同层多处重复的 rationale → 收敛到所属能力或助手的一次性说明。
7. 一段塞多规则 → 拆分或下沉到下层文档。
8. 过度强调(每段一个 **bold** / `CRITICAL` / "必须") → 强调留给改变行为的条款。

## 预算与校验

`scripts/doc_budgets.json` 定义预算。当前阈值:

| 文档 | 预算(词) |
|---|---|
| 根 `AGENTS.md` | 2000 |
| `docs/AGENTS.md` | 1200 |
| `docs/adr/README.md` | 1050 |
| `docs/specs/glossary.md` | 3000 |
| `docs/specs/harness-spine-spec.md` | 10000 |
| `docs/specs/run-live.md` | 4000 |

预算超限时先迁移不属于该层级的内容,再压缩重复表述;必要时调高阈值(同时更新预算文件并在 PR 描述中说明)。提交涉及 Markdown 目录、名称或链接的变更前,至少运行:

```sh
uv run python scripts/verify_md_links.py
uv run python scripts/verify_doc_budgets.py
uv run python scripts/check_doc_layering.py --strict
```

修改 ADR、公共规范或目录门禁时,运行相关测试;公共文档链接必须在同一变更中修复。
