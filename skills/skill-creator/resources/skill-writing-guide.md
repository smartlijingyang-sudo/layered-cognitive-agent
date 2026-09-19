# Skill 写作指南

改编自 Anthropic 官方 `skill-creator`（https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator/skills/skill-creator）。创建技能时先读本文件再动笔。

## 解剖结构

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - 可执行代码（确定性 / 重复任务）
    ├── references/ - 按需加载进上下文的文档
    └── assets/     - 输出用的文件（模板、图标、字体）
```

## 渐进披露

技能分三级加载：

1. 元数据（name + description）—— 始终在上下文中（约 100 词）
2. SKILL.md 正文 —— 触发时加载（理想 < 500 行）
3. 附属资源 —— 按需加载（不限大小；scripts 可执行而不必加载）

关键模式：

- SKILL.md 保持 < 500 行；快超限时再加一层层级，并写清下一步去哪。
- 在 SKILL.md 里明确引用资源文件并说明何时读。
- 大参考文件（>300 行）加目录。
- 多领域技能按变体组织 `references/`。

## description 是触发主机制

- description 要同时写「做什么」和「什么时候用」。所有 when-to-use 信息放这里，不放正文。
- 写得「pushy」一点：宁可过度触发也不要漏触发。例：「当用户提到仪表盘、数据可视化、内部指标，或想展示任何公司数据时，务必使用本技能，即使没有明确说 dashboard」。
- 简单一步操作可能不触发技能；复杂 / 多步 / 专业查询才稳定触发。

## 写作模式

- 用祈使句。
- 定义输出格式时给出精确模板。
- 给示例（Input / Output 对）。
- 解释「为什么」，少用大写 MUST / Never。向模型解释原因比硬性规定更有效。
- 保持精炼：删掉不承担工作的内容。

## 测试用例（可选但推荐）

技能草稿写好后，设计 2-3 个真实用户会说的测试提示词，与用户确认后运行。测试用例可存为 JSON：

```json
{
  "skill_name": "example-skill",
  "evals": [
    {"id": 1, "prompt": "用户的测试任务", "expected_output": "期望结果描述"}
  ]
}
```

在 LCA 里运行测试 = 在对话里用该技能实际执行一个任务，让用户评估输出；根据反馈回到 SKILL.md 迭代。