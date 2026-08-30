# ADR-0106: 命名宪法（Naming Constitution）

> **状态：** Proposed
> **日期：** 2026-08-30
> **主文档：** [docs/design/naming-constitution.md](../design/naming-constitution.md)
> **超集关系：** [`docs/specs/naming-conventions.md`](../specs/naming-conventions.md) 升级为本文的"语义后缀附录"。
> **配套 ADR：** [ADR-0105 包组织纪律](./0105-package-organization-discipline.md)

## 背景

仓库内命名存在三类问题：

1. **目录命名沿用 jargon 与缩写**：`dsh/`、`plane/`、`text/`、`face/`、`seam_definitions/`、`control_contributions/` 等无 v3 概念群归属。
2. **角色后缀混杂**：同一概念用 `*Impl` / `*Manager` / `*Wrapper` / `*Helper` 等无信息后缀；类名 / 文件名 / 目录名各说各话。
3. **既有规范只覆盖语义后缀**：[`docs/specs/naming-conventions.md`](../specs/naming-conventions.md) 只规定 `Protocol/Adapter/Coordinator/Registry/Manifest/Plan` 六个后缀，没覆盖目录命名、文件命名、函数命名、变量命名、枚举命名、跨群协作命名。

读者无法仅凭名字推断归属群、角色与对象，认知负担集中在"打开看 docstring"这一步。

## 决定

采用 **命名宪法**：所有命名（目录、文件、类、Protocol、函数、变量、常量、枚举）必须满足四维分解：

```text
名字 = [layer_] group_[role_] subject[_qualifier][_instance]
       (可选)   必选 必选 必选  (可选)       (可选)
```

强制规则：

1. **群归属**：每个名字必须能映射到 [v3 认知原语宪法 §3.2](../design/2026-08-19-cognitive-primitive-constitution-v3.md) 九群（State / Perceive / Think / Gate / Act / Memory / Collaboration / Journal / Composition）之一；映射不到属"横切"，需加 `[cross-cutting]` 标记。
2. **角色后缀**：必须从 [naming-constitution §4.1](../design/naming-constitution.md) 角色后缀表（30 个）选一个；新增后缀需 ADR。
3. **函数动词前缀**：必须从 [naming-constitution §8.1](../design/naming-constitution.md) 函数前缀表（14 个）选一个；无前缀的函数禁止合并。
4. **文件 ↔ 类一一对应**：`foo_bar.py` 必须定义 `FooBar`；`__init__.py` 必须显式 `__all__`，禁止 `__all__ = list(globals())`。
5. **禁止词**：`utils/helpers/common/misc/Impl/Manager/Wrapper/Helper/Info/Data` 等无信息后缀；`dsh/plane/text/face` 等 jargon 目录名（除 `LLM/JSONL/OTel/SSE/A2A/MCP` 白名单缩写）。

## 与既有规范的关系

| 既有规范 | 衔接 |
|---|---|
| `naming-conventions.md` | 升级为宪法的"语义后缀附录"，主规范由宪法承担 |
| `package-organization-discipline.md`（ADR-0105） | 互补：ADR-0105 约束规模与目录层级；本文约束名字的语义组成 |
| v3 认知原语宪法 | 本文是 v3 在命名层的细化，群归属由 v3 定义 |
| `AGENTS.md §5` | 保留方法 ≤ 200 行；本文进一步约束命名风格 |

## 与 ADR-0105 共用迁移路线

执行迁移时不分两份：

- **Phase A**（1 周）：零风险清扫（删空包、修 barrel、改 dsh 命名）。
- **Phase B**（3 周）：拆 8 个超大目录（每个 1 PR，自带 import 映射表 + 迁移脚本 + 命名合规检查）。
- **Phase C**（2 周）：命名规范化收敛（plane/runtime_plane、face/personas、5 个 phase_*/phase_graph 等）。
- **Phase D**（1 周）：CI 门禁落地（10 个 `scripts/check_*.py`）。
- **Phase E**（持续）：长尾收尾（`*Impl` / `*Manager` / `*Wrapper` 清理、文件名 / 类名一致性扫描）。

总迁移窗口 ≤ 8 周。

## CI 门禁

新增 / 复用 10 个 `scripts/check_*.py`（详见宪法 §12）：

- `check_filename_class_match.py`（核心）
- `check_no_utility_modules.py`
- `check_no_barrel_glob.py`
- `check_forbidden_suffix.py`
- `check_package_noun.py`
- `check_known_abbrev.py`
- `check_package_size.py`（与 ADR-0105 共用）
- `check_function_verb_prefix.py`
- `check_enum_str_value.py`
- `check_no_bare_strings.py`（复用既有）

接入 `lca-ops diagnose naming`，作为合并前置门禁。

## 豁免

- 既有迁移期可保留旧名，但必须提交 ADR 标注"过渡态 + 退役日期"，且 CI 报警而非阻断。
- 第三方集成沿用 vendor 命名（如 `openai_compat/`、`a2a/`）除外。
- 白名单缩写（`LLM` / `JSONL` / `OTel` / `SSE` / `A2A` / `MCP`）无需 ADR。

## 放弃的方案

- **只补命名规范不强制群归属**：缺群归属等于让读者继续靠"打开看 docstring"，宪法价值失去。
- **完全自命名（DSL 风格）**：复杂度高、IDE 支持差，读者仍要查表。
- **保留 `*Impl` / `*Manager` 等历史后缀**：这些后缀只在 Java/.NET 早期有信息量，在 Python 类型系统下完全无意义。

## 后果

正面：

- 任何名字都能在 0 上下文情况下推断归属、角色与对象。
- 新 PR 自动具备命名合规性（CI 阻断）。
- 与 v3 认知原语宪法、ADR-0105 包组织纪律形成完整治理链。

负面：

- 一次性迁移成本高（命名变更波及所有 import）。
- 第三方 / vendor 命名需明确白名单，避免误判。
- 命名宪法自身需要治理（不允许静默修改）。

## 索引

| 主题 | 文档 |
|---|---|
| 命名宪法（主） | [`docs/design/naming-constitution.md`](../design/naming-constitution.md) |
| 命名规范附录 | [`docs/specs/naming-conventions.md`](../specs/naming-conventions.md) |
| 包组织纪律 | [`docs/specs/package-organization-discipline.md`](../specs/package-organization-discipline.md) |
| 认知原语宪法 | [`docs/design/2026-08-19-cognitive-primitive-constitution-v3.md`](../design/2026-08-19-cognitive-primitive-constitution-v3.md) |
| ADR-0105 | [`docs/adr/0105-package-organization-discipline.md`](./0105-package-organization-discipline.md) |
