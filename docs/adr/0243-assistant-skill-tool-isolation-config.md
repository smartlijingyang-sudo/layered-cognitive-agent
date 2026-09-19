# ADR-0243 — 助理技能/工具隔离与可配置化

## 状态

**Proposed — 2026-09-19**

> **一句话**：把助理的技能与工具从「全局共享 + 策略过滤」升级为「Home 数据驱动、隔离、可编辑、可新增」——技能用硬链接 + 写时复制（COW）物化到 `{home}/skills/`，工具新增 `{home}/tools/` 自定义工具目录，运行时只从 Home 加载；全局库/平台注册表是只读内容源。

**Refines**：ADR-0242 §D4 / §D6 / §D9。
**不 supersede**：ADR-0187 / ADR-0242 主体决策仍有效；ADR-0048 / 0067 / 0167 不变。

---

## 1. 背景

### 1.1 实测缺陷

1. **助理目录看不到技能**。创建助理后 `{home}/skills/` 是空目录，`<available_skills>` 却显示全局库全部技能。用户问「为什么 agent 自己的目录下没有这些」——因为技能根本不在 Home，是全局共享的。
2. **技能删除不隔离**。`AssistantMergedSkillStore` 是「Home + 全局兜底」合并视图。即使从 Home 删除某个技能，全局兜底又让它出现在 `<available_skills>`，删除语义不成立。
3. **技能不可编辑**。自我管理工具族只有 create/delete/list，没有 edit。编辑一个技能会影响所有引用它的 agent。
4. **工具不可配置、不可新增**。Home 只有 `tools.yaml` 策略（allow/deny/grants），`list_assistant_tools` 只返回策略列表，不返回工具详情。没有「给这个 agent 新增一个工具」的入口。
5. **全局技能复制会漂移**。`inherit_from` 用 `shutil.copytree` 全量复制技能目录，空间浪费且无版本语义。

### 1.2 业界对照

| 模式 | 代表 | 空间 | 隔离 | 可编辑 |
|---|---|---|---|---|
| 硬链接农场 + 不可变内容 + COW | pnpm / npm | 低 | 强 | 好 |
| 分层 overlay + COW | Docker overlayfs | 低 | 强 | 好 |
| 内容寻址存储 | git / Nix | 最低 | 最强 | 好 |
| 每 agent 全量复制 | 简单实现 | 高 | 强 | 好 |
| 符号链接跟随全局 | 常见 CLI 插件 | 低 | 弱 | 中 |

LCA 采用 **硬链接 + COW**：兼容现有 `DiskSkillPackageStore` 目录结构，空间不重复，版本固定，编辑时断链复制。

---

## 2. 第一性原理

| # | 原则 | 落地 |
|---|---|---|
| P1 | 一个助理 = 它的 Home | 技能有效集与自定义工具都是 Home 数据，运行时只从 Home 装配 |
| P2 | 隔离是结构 | `{home}/skills/` 是助理的完整技能集；全局库只是只读内容源 |
| P3 | 空间不复制 | 全局技能以硬链接物化到 Home，不占额外空间 |
| P4 | 编辑是复制语义 | 修改共享技能前先断链（COW），全局与其他 agent 零感知 |
| P5 | 平台能力边界不变 | 自定义工具执行仍走沙箱/内置工具窄门，不引入新副作用路径 |
| P6 | 存量零打扰 | 无 `assistant_id` 路径行为不变 |

---

## 3. 决策

### D1 · 技能双层模型

- `~/.lca/skills/` 是**只读内容源**。包内容安装后不可变（content-hash 版本化）。
- `{home}/skills/` 是助理的**完整有效技能集**：
  - `local`：助理专属技能，`skill_overlay.install` 写入的真实文件。
  - `global_link`：从全局库**硬链接**物化的技能（`SKILL.md` / `resources/` / `manifest.json` 均为硬链接），不占额外空间。
- 创建时 `CreateAssistantRequest.initial_skills` 落地：默认把全局库全部技能物化为 `global_link` 并写 Home manifest 索引，保持既有可见性。
- 运行时 assistant-bound 的 `<available_skills>` / `activate_skill` **只读 Home 的 `skills/`**，不再 fallback 全局。`AssistantMergedSkillStore` 的全局兜底语义退役；全局库只作为链接来源。
- 删除 = 删除 Home 条目（unlink），不影响全局和其他 agent，也不会从全局兜底重新出现。
- 编辑 `global_link` = COW：先断链复制为 `local`，再编辑。
- 全局技能更新 = 写新版本；已链接 agent 保持旧 inode（版本固定），显式 re-link 才升级。

### D2 · 技能 manifest 扩展

`{home}/skills/<skill_id>/manifest.json` 增加 `source: "global_link" | "local"`。Home `manifest.json` 的 `skills` 索引条目增加同名字段。`build_manifest` 的 `extra_digests` 继续承载 `skills/<id>` 摘要（ADR-0242 D4 不变）。

### D3 · 工具双层模型

- **内置工具**：平台代码定义。Home 只存策略（`tools.yaml` allow/deny + `grants.yaml`）；详情是平台工具注册表的只读投影，不复制。
- **自定义工具**：`{home}/tools/<tool_id>/tool.json` 定义，具体、可编辑、隔离，与 `skills/` 对等。

`tool.json` schema（frozen Pydantic，未知字段 fail-closed）：

```json
{
  "name": "generate_weekly_report",
  "description": "生成周报并保存到工作区",
  "parameters": {
    "type": "object",
    "properties": { "week": { "type": "string", "description": "周范围" } },
    "required": ["week"]
  },
  "required_grant": "",
  "handler": {
    "kind": "builtin_preset",
    "builtin": "runCommand",
    "args": { "command": "python3 tools/generate_weekly_report/handler.py {{week}}" }
  }
}
```

`handler.kind` 闭集：

- `builtin_preset`：包装一个内置工具，`args` 与调用参数合并后执行。不新开副作用路径。
- `sandbox_script`：在 agent 工作区沙箱执行 `command`（复用 `run_skill_script` 的执行缝 `ensure_sandbox_runtime`）。

### D4 · 自定义工具写路径：AssistantToolOverlay

新增 `assistant.tool_overlay` capability + `AssistantToolOverlay` Protocol（contracts），实现只写 `{home}/tools/`，不触达全局：

- `create` / `update` / `remove` / `list_installed`。
- 写路径：校验 `tool.json` schema → 落盘 `{home}/tools/<id>/` → 更新 manifest `tools` 索引 + `revision_seq++` + `revisions/` 快照 + `assistant.profile.revised` EP。
- 与 `AssistantSkillOverlay` 同构；单类不得同时实现两个 overlay（沿用「无 God Catalog」纪律）。

### D5 · 运行时合并自定义工具

`ToolForkDispatchExecutor`（`lca/nodes/concept/tool_fork/dispatch.py`）在 `filter_tools_by_assistant` 之后增加一步：读取 `{home}/tools/*/tool.json`，实例化自定义工具并合并进 `ForkedTools`。自定义工具只对该 agent 可见。

### D6 · 自我管理工具族扩展

| 工具 | 落盘入口 | 敏感？ |
|---|---|---|
| `create_assistant_tool` | `tool_overlay.create` | 否，改完告知 |
| `update_assistant_tool` | `tool_overlay.update` | 否，改完告知 |
| `delete_assistant_tool` | `tool_overlay.remove` | 是，需用户确认 |
| `list_assistant_tools`（升级） | 返回内置 allow 工具详情 + 自定义工具详情 | 只读 |
| `edit_assistant_skill`（新增） | `skill_overlay` + COW 断链 | 否，改完告知 |

### D7 · Home 目录布局

`{home}/tools/` 加入占位子目录（`_HOME_SUBDIRS`）。模板不变。

---

## 4. 不变量

| ID | 内容 | 验证 |
|---|---|---|
| I-B13 | assistant-bound run 的 `<available_skills>` 只含 Home `skills/` 内容 | 集成：全局未挂载技能不出现 |
| I-B14 | 创建后 `{home}/skills/` 非空且每个条目有具体文件 | 集成：创建后 `SKILL.md` 可读 |
| I-B15 | 编辑 `global_link` 技能前必须先断链；全局文件内容不变 | 单元：COW 后 `~/.lca/skills/<id>/SKILL.md` digest 不变 |
| I-B16 | 删除 Home 技能不影响全局库与其他 agent | 集成 |
| I-B17 | 自定义工具只出现在该 agent 的 `tools` 数组 | 集成 |
| I-B18 | 自定义工具执行走沙箱/内置工具窄门 | 架构测试 |
| I-B19 | 无 `assistant_id` 路径行为不变 | web-standard 回归 |

---

## 5. 后果

正面：

- 助理目录有具体技能文件，可看、可编辑、可删除，且隔离。
- 工具可配置化、可新增，`list_assistant_tools` 返回详情。
- 空间不随 agent 数量膨胀（硬链接）。

负面 / 代价：

- 全局技能更新不会自动传播到已链接 agent（版本固定），需要显式 re-link。
- `sandbox_script` 自定义工具需要沙箱执行缝接线，涉及面较大，放后期。
- `AssistantMergedSkillStore` 语义变更会影响既有 assistant-bound 行为（默认挂载全部全局技能保持可见性，删除后不再兜底）。

删除条件：

- 若未来引入内容寻址存储（git 式），硬链接视图可整体替换。

---

## 6. 实施 PR 序列

### PR-1 · ADR 合入 + README 登记

### PR-2 · 技能物化与隔离（D1/D2/I-B13/I-B14/I-B16）

- `catalog.create` 落地 `initial_skills`：物化全局技能为硬链接 + 写 manifest 索引。
- `_home_layout`：manifest `skills` 索引支持 `source`。
- `AssistantMergedSkillStore`：assistant-bound 只读 Home store。
- `_copy_inherited_snapshot`：`global_link` 用硬链接复制，`local` 用快照复制。

### PR-3 · 技能 COW 编辑（D6/I-B15）

- 新增 `edit_assistant_skill` 工具：断链复制 → 编辑 SKILL.md → 重算 digest。
- `skill_overlay.remove` 处理 `global_link`（unlink 即可，不动全局）。

### PR-4 · 工具 schema 与 overlay（D3/D4/D7）

- `{home}/tools/` 占位目录。
- `ToolSpec` / `ToolHandlerSpec` frozen Pydantic 模型（contracts）。
- `assistant.tool_overlay` capability + `AssistantToolOverlay` Protocol + plugin 实现。

### PR-5 · 自定义工具运行时合并（D5/I-B17/I-B18）

- `ToolForkDispatchExecutor` 合并 `{home}/tools/` 工具。
- 自定义工具执行：`builtin_preset` 包装内置工具；`sandbox_script` 复用沙箱执行缝。

### PR-6 · 自我管理工具族（D6）

- `create_assistant_tool` / `update_assistant_tool` / `delete_assistant_tool`。
- `list_assistant_tools` 升级为返回详情。

---

## 7. 否决的替代方案

| 方案 | 结论 | 原因 |
|---|---|---|
| 每 agent 全量复制全局技能 | 否 | 空间浪费、版本漂移 |
| 符号链接跟随全局 | 否 | 删除/编辑语义脆弱，全局更新意外传播 |
| 内容寻址存储一步到位 | 否（当前阶段） | 重写 store 成本高；硬链接兼容现有目录结构 |
| 自定义工具直接写 Python 代码到 Home | 否 | 引入任意代码执行路径，绕过窄门；只允许声明式 handler |

---

## 8. 开放问题

1. 默认挂载全部全局技能 vs 角色卡推荐子集。建议默认全部（保持可见性），后续按模板收敛。
2. `sandbox_script` 的沙箱执行缝复用 `run_skill_script` 的 `ensure_sandbox_runtime`，需要把 `skill_id` 依赖解耦。
3. `re-link` 升级全局技能的 UI/工具路径本期不做。

---

## 修订记录

| 日期 | 变更 |
|---|---|
| 2026-09-19 | 初稿，编号 0243，登记 README 索引 |