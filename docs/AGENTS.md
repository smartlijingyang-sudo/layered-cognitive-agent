# LCA Documentation Standard

本文定义 LCA 文档的目录归属、写作要求和验证门禁。目录导航见 [documentation map](specs/documentation-map.md)。

## 目录归属

| 位置 | 只承载 | 不承载 |
|---|---|---|
| `AGENTS.md` | 每个开发会话都需遵守的高频规则和入口链接 | 过程记录、方案草稿、实施报告 |
| `docs/adr/` | 已采纳、替代或废弃的架构决策 | 任务分解、验收过程、会议记录 |
| `docs/specs/` | 当前有效的协议、操作指南、术语和参考 | 历史理由、一次性调查 |
| `docs/design/` | 宪法级或长期有效的设计说明 | 实施状态、复盘报告 |
| `docs/observability/` | Journal、Trace、Metrics 和 Projection 的现行规格 | 通用架构叙述 |
| `history/YYYY-MM/<topic>/` | 已结束的计划、研究笔记、执行记录、审计和交付报告 | 当前规范或仍有效的决策 |
| `roles/`、`skills/`、`deploy/` | 其所属组件的就近说明、模板或操作文档 | 跨组件架构决策 |

> **归位原则：一个事实只保留一个权威位置。** 决策理由归入 ADR；当前契约和操作步骤归入 specs 或 observability；已结束工作的过程材料归入 history；代码就近说明保留在所属组件目录。

## 命名与链接

所有新文档使用小写 kebab-case 文件名；日期敏感的历史材料以 `YYYY-MM-DD-` 开头，或收纳于对应的 `history/YYYY-MM/<topic>/` 目录。历史目录使用 `README.md` 说明范围和索引。文档链接必须使用相对路径，禁止裸文件名和固定 commit 的 GitHub `blob/<sha>` 链接。

`docs/` 根目录只允许 `AGENTS.md`。不得重新创建 `docs/plans/`、`docs/research/`、`docs/status/` 或 `docs/reports/`；这些材料若需保留，应进入 `history/`。新增 ADR 前先判断决定是否已经由现有结构表达；新增文档前先判断事实是否能归入既有文档。

## 写作要求

写当前事实和可验证的契约，不写变更叙事。类型、失败语义、时序、所有权和外部后果应明确；实现演练、重复解释、过期状态和无期限 TODO 应删除或归档。交叉引用链接到唯一权威文档，不复制同一规则。

## 预算与校验

`scripts/doc_budgets.json` 定义预算；当前 ADR 索引预算为 950 词，以容纳完整且受测试守护的决策表。预算超限时先迁移不属于该层级的内容，再压缩重复表述。提交涉及 Markdown 目录、名称或链接的变更前，至少运行：

```sh
uv run python scripts/verify_md_links.py
uv run python scripts/verify_doc_budgets.py
uv run python scripts/check_doc_layering.py --strict
```

修改 ADR、公共规范或目录门禁时，运行相关测试；公共文档链接必须在同一变更中修复。
