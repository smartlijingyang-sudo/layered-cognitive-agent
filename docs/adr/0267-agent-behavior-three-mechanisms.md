# ADR-0267: Agent 行为三机制补齐（对齐 muse 架构）

- **状态**: Proposed
- **日期**: 2026-10-02
- **背景**: traces/runs 实证分析（run_15ad694186ba/3ff00379b598/9875a88d22c6）发现三处系统性差距，见 backlog todo-16。

## 1. 工具失败降级层

**问题**: `composioConnect` 403 后整轮 failed。工具失败 = run 失败，无降级。

**机制** (`lca/cognition/body/degradation/`):
- `DegradationKind`: PERMISSION / TRANSIENT / DETERMINISTIC / NOT_FOUND
- `classify_error()`: 精确分类（403/401→PERMISSION，关键词匹配）
- `degrade()`: 失败转结构化 `DegradedResult`，永不抛异常
- 不变量：单工具失败永不直接杀死 run；agent 总有机会优雅降级

**muse 思想**: 工具失败是数据，不是崩溃。fail-closed 在工具（不谎称成功），fail-open 在 run（不杀死对话）。

**保留 LCA 优秀**: 既有重试机制（transient/deterministic 区分）不动；降级层在其之上。

## 2. 记忆加权呈现

**问题**: 记忆写了但不用。新闻轮搜了"跨境电商"，呈现时未按用户画像加权。

**机制** (`lca/cognition/presentation/`):
- `weight_items()`: 用户画像关键词匹配 → 相关性加分
- 中文 bigram 模糊匹配（"电商出海" vs "跨境电商"）
- `format_with_relevance()`: 高相关项标注"与你相关"，提示 agent 点评
- 确定性、可审计（matched_keywords 透明）

**muse 思想**: 记忆为用而存。机制自动应用用户上下文，不依赖模型"记得"去用。

**保留 LCA 优秀**: 记忆写入纪律（先查后写、dedupe_key）不动；本机制只补"读"侧。

## 3. 推理经济性

**问题**: Reasoning 复述规则条文（"根据我的记忆写入规则，我需要：1、2、3…"），token 浪费且思考懒惰。

**机制** (`lca/plugins/prompts/sections/memory.py`):
- 规则从过程式改为约束式（删步骤复述，留规范效力）
- 新增"思考经济性"节：规则是约束不是解说词；思考对准目标，不复述条文
- 保留测试断言的标题关键词（ADR-0255 一致性）

**muse 思想**: 规则内化为直觉，不外化为背诵。能写进代码的机制不写进 prompt。

**保留 LCA 优秀**: 检索义务、写盘铁律、防幻觉闸门的规范内容不动；只改表述风格。

## 验收

- T1: `degrade()` 对 composio 403 案例返回 PERMISSION + 中文 user_guidance
- T2: `weight_items()` 对电商用户画像正确置顶关税新闻
- T3: `test_memory_decision_gate.py` 全绿（标题关键词保留）
- T4: 三机制单元测试全绿
