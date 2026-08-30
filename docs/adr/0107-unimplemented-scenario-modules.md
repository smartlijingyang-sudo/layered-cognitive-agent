# ADR-0107: scenario plugin modules never implemented (tracked gap)

> **状态：** Proposed
> **日期：** 2026-08-30
> **触发：** Phase A audit found 4 bundle YAMLs referencing modules that do not exist in any git history.

## 背景

Phase A 修复 `lca.plugins.memory` 时，在 bundle YAML 中发现 4 个 scenario 引用的 memory module 缺失：

| YAML | `$module` |
|---|---|
| `bundles/scenario-memgpt.yaml:8` | `lca.plugins.memory.four_layer` |
| `bundles/scenario-standard.yaml:15` | `lca.plugins.memory.four_layer` |
| `bundles/scenario-voyager.yaml:17` | `lca.plugins.memory.four_layer` |
| `bundles/scenario-lats.yaml:27` | `lca.plugins.memory.tree_cache` |

扩大 grep 显示更多 scenario plugin module 也缺失，全部与 [v3 认知原语宪法 §13.5 典型用例](../design/2026-08-19-cognitive-primitive-constitution-v3.md) 描述的能力对应：

| Scenario | 缺失 module |
|---|---|
| memgpt | `lca.plugins.memory.four_layer`, `lca.plugins.policy.compaction`, `lca.plugins.budgeter.memgpt` |
| lats | `lca.plugins.brain.lats`, `lca.plugins.critic.value_network`, `lca.plugins.memory.tree_cache` |
| voyager | `lca.plugins.skill.auto_acquire`, `lca.plugins.memory.four_layer`, `lca.plugins.tools.bash`, `lca.plugins.tools.file_write`, `lca.plugins.tools.test_run` |
| standard | `lca.plugins.brain.modular`, `lca.plugins.memory.four_layer` |

`git log --all -- lca/plugins/memory/four_layer.py` 等命令返回空——**这些 module 从未存在过**。也就是说：

- 这些 scenario 当前**无法 resolve**：profile 加载会爆 `ModuleNotFoundError`。
- v3 宪法 §13.5 描述的能力（MemGPT paging、Voyager skill acquisition、LATS MCTS、standard four-layer memory）**只是 spec 层存在，从未落地**。

这是 Phase A 之前就存在的 pre-existing gap，**不是 Phase A 引入的回归**。

## 决定

**短期（本次 PR 范围内）：**

1. 创建 2 个 stub module 让 `$module:` 路径至少可以 resolve：
   - `lca/plugins/memory/four_layer.py` —— `@plugin` 注册 + `setup()` 抛 `NotImplementedError`
   - `lca/plugins/memory/tree_cache.py` —— 同上
2. stub 必须有清晰错误消息，指明 "Phase X 待实现，见 ADR-0107"。

**中期（不在本次 PR）：**

3. 4 个 scenario YAML 中引用的其他缺失 module（`brain.lats`、`skill.auto_acquire` 等）需要在各自对应的场景实现 PR 中补齐。每个模块单独 ADR。
4. ADR-0107 仅跟踪 `four_layer` 和 `tree_cache` 这 2 个；其他缺失模块后续各自开 ADR。

**长期：**

5. 每个 scenario 的实际算法实现（MemGPT paging、LATS MCTS、Voyager skill acquisition、standard four-layer memory）需要单独的工作量评估。这些是 v3 宪法 §13.5 的真实功能实现，不是 stub 错误消息能替代的。

## 替代方案

- **A. 直接从 bundle YAML 删除引用**：简单，但破坏 scenario 加载（用户无法使用 v3 §13.5 描述的能力）。违反 spec。
- **B. 删除整个 scenario bundle**：更激进，但失去 scenario 模板供未来实现。
- **C. 选 C（采用）**：stub + ADR 跟踪，bundle 可以 resolve 但运行时清晰报错。

## 后果

正面：

- Profile 解析不会爆 `ModuleNotFoundError`；运行时报错明确指向 ADR-0107。
- 把 pre-existing gap 显式化（之前是隐藏失败，现在是已知失败）。

负面：

- Bundle YAML 引用的其他缺失 module（10+ 个）仍未处理；用户运行这些 scenario 时仍会爆 `ModuleNotFoundError`。
- Stub 不提供任何实际功能。

## 范围限定

ADR-0107 **只跟踪**：
- `lca.plugins.memory.four_layer`
- `lca.plugins.memory.tree_cache`

ADR-0107 **不跟踪**（需要各自 ADR）：
- `lca.plugins.policy.compaction`
- `lca.plugins.budgeter.memgpt`
- `lca.plugins.brain.lats`
- `lca.plugins.critic.value_network`
- `lca.plugins.skill.auto_acquire`
- `lca.plugins.tools.bash`
- `lca.plugins.tools.file_write`
- `lca.plugins.tools.test_run`
- `lca.plugins.brain.modular`

## 实现

本次 PR 在 `lca/plugins/memory/` 下创建：

- `four_layer.py` —— 占位 stub
- `tree_cache.py` —— 占位 stub

每个 stub 必须：
1. 用 `@plugin(...)` 装饰器注册（与正常 plugin 一致），让 bundle resolve 通过。
2. `setup()` 函数体内立即 `raise NotImplementedError(...)`，错误消息含 ADR 编号。
3. `Config` 类保留为 pydantic `BaseModel`，支持 bundle YAML 传入的 config 字段（即使还没用到）。

## 索引

- 触发审计：`docs/specs/package-organization-discipline.md` §10.3（命名违规清单）
- 关联 Phase A：commit `a332841b`
- 上游规范：[v3 认知原语宪法 §13.5](../design/2026-08-19-cognitive-primitive-constitution-v3.md)
