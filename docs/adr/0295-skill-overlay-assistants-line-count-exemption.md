# ADR-0295：skill_overlay / assistants 行数上限临时豁免（todo-88 裁决）

> **Status: Proposed**（2026-10-09 起草，iter-arch 02:09 轮裁决）

## 1. 问题

`tests/scenario/code/test_code_conventions.py::TestFileLineCountLimit` 对 `lca/` 下文件设 250 有效代码行上限；超限即红，逃生舱为 `_LINE_COUNT_EXEMPT` 字典登记（测试 message 要求引用 ADR）。

2026-10-09 tests lane 全量 sweep 发现两文件超限（todo-88，`main@1b82c8a6a` 实证，本轮复验仍超限）：

- `lca/contracts/protocols/assistant/skill_overlay.py`：285 有效行 —— 5 dataclass（SkillSource / SkillInstallReceipt / SkillActivationReceipt / SkillRelinkReport）+ 2 errors + `AssistantSkillOverlay` Protocol（4 方法）
- `lca/infrastructure/cli/commands/ops/assistants.py`：304 有效行 —— typer `register` + soul 系命令（history/diff/rollback）+ skill/relink 系命令 + request/emit/list/show/create helpers

两文件最新实质改动均为 skill 主题新鲜代码（`997705416`，2026-10-08，agy/李超，ADR-0243 relink 落地）。

## 2. 选项

- (a) 拆分模块：`skill_overlay.py` → 类型迁 `skill_overlay_types.py`，Protocol 留守；`assistants.py` → `assistants_soul.py` / `assistants_skills.py`；同步更新 `lca/plugins/assistant/skill/overlay/*` 等消费方的 import。
- (b) `_LINE_COUNT_EXEMPT` 临时豁免，引用本 ADR。

## 3. 裁决：取 (b)

1. **不 churn 他人新鲜代码**：两文件刚于 2026-10-08 落盘，skill overlay 主题仍在演进；此时拆分 import 面制造无谓冲突面。quality lane 已明确不擅自拆分他人新鲜代码、不擅自登记豁免——拆分执行权交还后仍需等主题沉淀。
2. **内聚论证**：`skill_overlay.py` 是 protocol 定义文件——dataclass / errors 与其服务的 Protocol 天然同属一个内聚单元，硬把类型拆出去是反内聚的；`assistants.py` 是 typer 命令聚合点（命令注册表），同类已有豁免先例（`cli/commands/runs/tools.py`："CLI 工具子命令集中 registration、provider 装载、CLI 渲染、命令装配"）。
3. **机制即为此设计**：测试 message 明示"如需临时豁免，请在 `_LINE_COUNT_EXEMPT` 中登记并引用 ADR"；豁免表有活跃管理先例（52 → 23 死键清理，见测试文件头注记）。

## 4. 登记指令（交 quality lane 执行，arch lane 不动 tests/）

在 `_LINE_COUNT_EXEMPT` 追加（键为仓库相对路径，理由引用本 ADR）：

- `lca/contracts/protocols/assistant/skill_overlay.py`："AssistantSkillOverlay Protocol 与其 5 dataclass / 2 errors 同属单一内聚定义单元，硬拆反内聚（ADR-0295）"
- `lca/infrastructure/cli/commands/ops/assistants.py`："typer 命令聚合点（soul + skill/relink 系），与 runs/tools.py 豁免同构（ADR-0295）"

## 5. 诚实边界（临时性）

- 豁免是临时的，不改变"超限默认红"的规则；豁免表继续接受死键清理。
- Revisit 触发（任一满足即由 arch lane 重审，仍可选 (a)）：任一文件有效行超过 400；或 skill-overlay 主题沉淀出自然模块边界。
- 本 ADR 为 Proposed：登记动作即视为采纳 (b)；若李超/ Athena 否决，改走 (a) 拆分，届时由 quality lane 执行。
