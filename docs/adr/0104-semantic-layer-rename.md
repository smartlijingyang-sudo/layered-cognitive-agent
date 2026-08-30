# ADR-0104: lca 一级包名语义化

## 状态

Accepted

## 背景

LCA 当前的一级包名采用 `lca.infrastructure` / `lca.cognition` / `lca.runtime` / `lca.agent` / `lca.application` 编号层。

- 编号层能表达顺序（"L0 → L4 越来越上层"），但**难以表达职责**——新人需要先背顺序，再查 ADR-0001 才能知道每个层做什么
- 5 个 ADR 文本（0001、0084、0085、0094、0095 等）反复出现"lca.runtime 禁依赖 lca.agent"这类规则，**对读者没有任何语义提示**
- 业界惯例（Linux 内核、Spring、Hexagonal Architecture、Django）都按"职责"命名层而非编号

## 决策

将 5 个编号层**一次性切换**为语义名，**不留 shim、不留兼容期**：

| 旧 | 新 |
|---|---|
| `lca.infrastructure` | `lca.infrastructure` |
| `lca.cognition` | `lca.cognition` |
| `lca.runtime` | `lca.runtime` |
| `lca.agent` | `lca.agent` |
| `lca.application` | `lca.application` |

**保留不变**（不重命名）：

- `lca.contracts`（数据契约层，公共入口）
- `lca.harness`（运行时外壳）
- `lca.plugins`（可装配行为集合）
- `gateway`（HTTP/SSE 入口，薄适配层）

**改名带来的副作用**：

- 外部消费方（profile 作者、plugin 作者、LobeHub patch 维护者）必须一次性升级
- `lca.contracts`、`lca.harness`、`lca.plugins`、`gateway` 的 public API 不变
- ADR-0001 作为历史档案保留；新 ADR-0104 替代
- import-linter contracts 的 layers 顺序更新为新名

## 影响面盘点

按 `grep -rln "lca\.layer[0-4]_" lca/ gateway/ tests/ profiles/ deploy/ docs/` 统计：

- **共 ~829 个文件引用旧名**（实际执行时动态统计）
- 代码层：所有 `lca.layer*` import 改新名
- 配置层：`pyproject.toml` import-linter contracts 的 layers 列表改新名
- 文档层：`docs/AGENTS.md`、`docs/specs/naming-conventions.md`、`docs/adr/0001-five-layer-separation.md`、`docs/design/*` 中所有提及 `layer0/1/2/3/4` 的位置
- Profile：`profiles/*.yaml`（若硬编码路径）
- Plugin 内部：`lca/plugins/`（若引用）
- 部署：`deploy/lobehub/patches/` 同步
- 测试：`tests/` 全量

## 原子切换清单

PR 必须同时改：

1. **代码层**：`git mv` + 全局 `sed -i` 替换 import
2. **配置层**：`pyproject.toml [tool.importlinter.contracts]` 第 1 条 layers
3. **文档层**：AGENTS.md、specs、adr、design、architecture
4. **Profile**：`profiles/*.yaml`
5. **Plugin 内部**：`lca/plugins/` 内 import
6. **部署**：`deploy/lobehub/patches/`
7. **测试**：`tests/` 内 import
8. **L4 check**：`pyproject.toml [tool.lca.package_contracts.*]` 段 forbidden_dependencies 路径
9. **ADR 自身**：本 ADR Accepted 时间戳
10. **CHANGELOG**：`CHANGELOG.md` 新增 Breaking Changes 段
11. **root AGENTS.md §3** 层依赖图

## 实施方式

- 5 个原子 PR，每个 PR 切换 1 个映射（`rename/layerN-X` 分支）
- 每个 PR 独立 `git revert -m 1 <merge-commit>` 即可回退
- 迁移辅助脚本：`scripts/migrate_layer_rename.py`（dry-run + execute + rollback）

## 一次性 vs 渐进式

**选择一次性**（不留 shim）：

- 避免 6–12 个月内持续维护"老路径兼容层"的负担
- 强制外部消费方一次性升级，避免"无限期兼容"陷阱
- 仓库内部用 `grep -rn "lca\.layer[0-4]_"` 立即验证"零残留"
- ADR-0002 已有"hook 自由主义被宪法取代"先例，闭集纪律延伸到包名一致

## 风险

| 风险 | 缓解 |
|---|---|
| 外部消费方未升级 | CHANGELOG + 迁移指南 + 通知 |
| `git mv` 与 import 同步改，单独 revert 困难 | 必须 `git revert -m 1 <merge-commit>` 整组 |
| import-linter 漏改 | Task 3-7 原子 PR 内每步验证 |
| 文档未同步导致"代码已迁，文档未迁"中间态 | Task 9-11 强制同步 + 验收清单 |

## 回退策略

- 单个 PR 失败：`git revert -m 1 <merge-commit>`（整组 revert，详见 plan §5.1）
- 整体回退：5 个 PR 全部 revert，仓库恢复原状
- 注：`git mv` 不可单独 revert（import 也改了），必须整组

## 关联

- **前置**：Phase 1 完成（L4 check 全绿；90 个包有 L1/L2 契约）
- **后续**：Phase 3（filename linter + 命名规范）
- **关联 ADR**：
  - ADR-0001（五层单向）— 本 ADR 替代其层名部分
  - ADR-0061（plugin manifest resolve/boot）— 本 ADR 不影响 plugin 加载
  - ADR-0096（journal protocol layer everything pluggable）— 本 ADR 不影响 journal
  - ADR-0103（locked surface and port policy）— 本 ADR 不影响 locked surface

## 决策记录

- 提出：2026-08-30
- 状态：Accepted（待实施；实施时记录合并时间）
