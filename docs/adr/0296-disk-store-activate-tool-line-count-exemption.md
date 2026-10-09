# ADR-0296：skills disk store / activate tool 行数上限临时豁免（todo-95 裁决）

> **Status: Proposed**（2026-10-09 起草，iter-arch 14:09 轮裁决）

## 1. 问题

`tests/scenario/code/test_code_conventions.py::TestFileLineCountLimit` 对 `lca/` 下文件设 250 有效代码行上限；超限即红，逃生舱为 `_LINE_COUNT_EXEMPT` 字典登记（测试 message 要求引用 ADR）。

2026-10-09 tests lane 全量 sweep 发现两文件超限（todo-95，`main@0127c7120` 实证，本轮在 `main@1cc01a1ac` 复验仍超限——316 / 266）：

- `lca/infrastructure/skills/disk/store.py`：316 有效行 —— `DiskSkillPackageStore`（同时实现 `SkillPackageInstaller` + `SkillPackageStore` 两 Protocol：`__init__` / `root` / `list_installed` / `get` / `read_resource` / `resource_files` / `install_package` / `materialize_link` / `update_package_meta`）+ 包磁盘路径语义 helper（`sanitize_skill_id` / `content_hash` / `safe_rel_path` / `is_canonical_rel_path` / `require_canonical_rel_path` / `walk_skill_source_files` / `_strip_resources_prefix` / `_to_resource_rel` / `_rmtree`）
- `lca/infrastructure/tools/skills/activate/tool.py`：266 有效行 —— `SkillActivateTool`（Tool：`__init__` / `_resolve_package`）+ 激活引用构建 helper（`usable_skill_resources` / `build_skill_references_section` / `_is_agent_usable` / `_script_paths`）

## 2. 选项

- (a) 拆分模块：`store.py` → 路径安全 helper 迁出（如 `paths.py`），store 类留守；`tool.py` → 引用构建 helper 迁 `references.py`，工具类留守；同步更新消费方 import。
- (b) `_LINE_COUNT_EXEMPT` 临时豁免，引用本 ADR。

## 3. 裁决：取 (b)

1. **立案归因两处错配，独立复验纠正**：todo-95 立案称 "RA-057（skill-package write guard 落地）推高 store.py / RA-052（activation_ref 接线）推高 tool.py"——复验：RA-057（`70c4f1461`）**未动 store.py**（write guard 落在 `standing_path.py` + `path/policy.py` + executor），RA-052（`02c781f76`）**未动 tool.py**（动的是 doctor/`compile_dry_run.py`）。实际增长驱动（`9671aba59..0127c7120` 逐 commit `-- <file>` 实证）：store.py ← RA-059（hardlink materialization 一等 seam，`2333bfbff`）、RA-075（frontmatter 解析归一）、RA-076（safe_rel_path 策略收敛）、RA-077（importer fail-loud）、RA-078（构造/mkdir 分离）、RA-080（三处目录 walk 收敛）；tool.py ← RA-055（content injection 门控，`f113c2f26`，+48）。均为 raphy 技能系统收敛轮的刻意功能增量，非偶然膨胀。
2. **内聚论证**：`store.py` 是"包在磁盘上"语义的单一单元——`DiskSkillPackageStore` 双 Protocol 实现与其路径安全 helper（canonical rel path / resources 前缀剥离 / 源文件 walk）天然同属；RA-076 刚把 `safe_rel_path` 策略收敛进本模块，此时把 helper 拆出去等于撤销一次刻意收敛。`tool.py` 是"技能激活"语义的单一单元——`SkillActivateTool` 与其激活引用构建 helper 同属；仅超 16 行，拆分收益不成比例。
3. **主题仍在演进**：skills 主题当日仍在 churn（本轮 raphy RA-081..096 同轮仍在碰 skills/seam，如 RA-086 tool-effects 收敛、RA-081 box 边界）；此时拆 import 面制造无谓冲突面。另 `safe_rel_path` 的归宿是独立议题（quality 03:09 轮观察：下沉到 `lca/infrastructure/path.py`），不应借行数上限之名顺手做。
4. **机制即为此设计**：测试 message 明示"如需临时豁免，请在 `_LINE_COUNT_EXEMPT` 中登记并引用 ADR"；先例 ADR-0295（todo-88 裁决 → todo-90 登记执行）。

## 4. 登记指令（交 quality lane 执行，arch lane 不动 tests/）

在 `_LINE_COUNT_EXEMPT` 追加（键为仓库相对路径，理由引用本 ADR）：

- `lca/infrastructure/skills/disk/store.py`："DiskSkillPackageStore 双 Protocol 实现 + 包磁盘路径语义 helper 同属单一内聚单元（RA-076 刚收敛 safe_rel_path 策略进本模块，硬拆反收敛；ADR-0296）"
- `lca/infrastructure/tools/skills/activate/tool.py`："SkillActivateTool + 激活引用构建 helper 同属激活语义单元，仅超 16 行，拆分收益不成比例（ADR-0296）"

## 5. 诚实边界（临时性）

- 豁免是临时的，不改变"超限默认红"的规则；豁免表继续接受死键清理。
- Revisit 触发（任一满足即由 arch lane 重审，仍可选 (a)）：任一文件有效行超过 400；或 skills 主题沉淀出自然模块边界（如 `safe_rel_path` 下沉方案落地时一并重审）。
- 本 ADR 为 Proposed：登记动作即视为采纳 (b)；若李超/ Athena 否决，改走 (a) 拆分，届时由 quality lane 执行。
