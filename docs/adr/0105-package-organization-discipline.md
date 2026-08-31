# ADR-0105: Python 包目录规模与命名规范（8/10/15 规则）

> **状态：** Proposed
> **日期：** 2026-08-30
> **配套规范：** [docs/specs/package-organization-discipline.md](../specs/package-organization-discipline.md)

## 背景

仓库内 Python 包目录普遍存在三类问题：

1. **平铺过载**：`gateway/runs/`（57 文件）、`lca/infrastructure/observability/journal/`（23 文件）、`lca/contracts/protocols/`（53 文件）等单目录直接堆 20+ 个 `.py`。
2. **命名混乱**：3 字母缩写（除白名单）、单字（`plane`/`text`/`state`/`face`）、jargon（`seam_definitions`/`seams`）、1 字母差重名（`compose` vs `composer`）。
3. **结构 bug**：空包（`lca/plugins/team_lead/`）、损坏包（`lca/plugins/memory/` 无 `__init__.py`）、空目录树（`lca/packages/identity/anonymous_user_id/`）、自动 barrel（`lca/contracts/protocols/__init__.py` 314 行用 `globals()` 自动 `__all__`）。

这些问题导致：

- 新读者无法仅凭目录名定位代码（认知负担高）。
- 拆分动作没有量化阈值，靠"心情判断"。
- 没有 CI 门禁兜底，越线只能靠 review。

## 决定

采用 **8 / 10 / 15 规则**：

| 直接 `.py` 数 | 处置 |
|---|---|
| ≤ 8 | 正常 |
| 9–10 | 预警，PR 描述必须确认无职责混杂 |
| > 10 | 必须按 v3 概念群或子职责拆分 |
| > 15 | 必须拆分；豁免必须 ADR 文档化原因、迁移计划、退役日期 |

同时强制：

- 文件 ≤ 400 行、类 ≤ 200 行、函数 ≤ 50 行、嵌套 ≤ 4 层。
- 顶层业务包 ≤ 10 个，每个包一级子模块 ≤ 10 个。
- 目录命名对齐 [v3 认知原语宪法](../design/2026-08-19-cognitive-primitive-constitution-v3.md) §3.2 的九群（State / Perceive / Think / Gate / Act / Memory / Collaboration / Journal / Composition）。
- 禁用 `utils.py` / `helpers.py` / `common.py` / `misc.py` / `shared.py` 等无信息命名。
- 禁止 `__init__.py` 用 `__all__ = list(globals())` 自动 barrel。

具体违规清单、拆分模板、迁移路线见 [package-organization-discipline.md](../specs/package-organization-discipline.md) §10–§12。

## 与既有规范的关系

| 既有约束 | 衔接 |
|---|---|
| ADR-0001 五层单向 | 不变；本规则在每层内加规模约束 |
| ADR-0015 contracts 纯净 | 不变；额外约束 contracts 子目录规模 |
| `naming-conventions.md` 语义后缀 | 不变；补充"包名 = 概念群关键词" |
| AGENTS.md §5 文件 ≤ 1500 行、方法 ≤ 200 行 | 收紧：400 / 200 / 50 |
| Harness Spine plugin-everything | 不变；plugin 目录同样受 8/10/15 约束 |

## 豁免

仅以下两类可以越线：

1. **概念唯一性**：目录对应一个不可拆分的稳定概念。仍需 ADR 文档化原因。
2. **过渡期兼容**：迁移中目录，ADR 标注"过渡态 + 退役时间"。

不可豁免：

- `__init__.py` 自动 barrel → 必须改显式 `__all__`。
- 空包 / 损坏包 → 必须删除或修复。
- `utils.py` / `helpers.py` 等新增 → 必须改名。

## CI 门禁

新增 8 个 `scripts/check_*.py`：

- `check_package_size.py`（8/10/15 阈值）
- `check_no_barrel_glob.py`（禁止 `__all__ = list(globals())`）
- `check_no_utility_modules.py`（禁止 `utils/helpers/common/misc`）
- `check_package_noun.py`（包名对齐 v3 概念群关键词）
- `check_known_abbrev.py`（缩写白名单）
- `check_package_integrity.py`（空包 / 损坏包）
- `check_tests_layout.py`（`tests/` 平铺 ≤ 30）
- `check_readme_filled.py`（README 脚手架占位符）

接入 `lca-ops diagnose package-organization`，作为合并前置门禁。

## 放弃的方案

- **只设上限，不分阈值**：单阈值规则容易"差一个就违规"，但缺预警和豁免通道，灵活性差。
- **保留自动 barrel 并加 lint**：自动 barrel 的语义模糊性无法靠 lint 修复，必须物理改写。
- **只约束直接 .py，不动子目录**：`tests/` 这样的"叶子大目录"是主要受害者，必须一并约束。
- **靠 PR review 兜底**：缺少量化规则，review 主观性大；必须用 CI 强制。

## 后果

正面：

- 任何目录都能在 1 秒内通过"打开看 8 个文件"完成认知。
- 拆分动作由 CI 强制，不再依赖 review 主观判断。
- 命名与 v3 概念群对齐，认知一致性显著提升。

负面：

- 一次性迁移成本高（约 9 个超大目录 + 17 个命名违规）。
- 历史 import 路径可能需要 deprecation 周期。

## 迁移路线

详见 `package-organization-discipline.md` §12：

- **Phase A**（1 周）：删除空目录、修复损坏包、修 barrel。
- **Phase B**（3 周）：拆分 8 个超大目录（每个一个 PR）。
- **Phase C**（2 周）：命名规范收敛。
- **Phase D**（1 周）：CI 门禁落地。
- **Phase E**（持续）：长尾收尾。

总迁移窗口 ≤ 8 周。
