# ADR-0019: 架构审查后的死代码清理与 Registry 语义统一

## 状态
Accepted

## 背景
2026-07 架构审查发现：五层依赖与 Protocol-first 纪律良好，但存在可验证的技术债——
废弃桩代码、过渡期别名未摘、`Supervisor` 空壳子类、Registry 家族 `resolve()` 语义不一致、
部分文件名不能反映职责。

## 决定

### 1. 删除废弃 GroupChat 模块
`layer3_agent/group_chat.py` 的 `build_group_chat_graph` 永远抛 `NotImplementedError`，
无正常调用路径。删除模块与对应测试；GroupChat 拓扑放弃理由见 ADR-0006。

### 2. 摘除过渡期别名（ADR-0016 遗留）
| 删除项 | 替代 |
|---|---|
| `RegistryProtocol` | `NamedRegistryProtocol` |
| `FallbackHandler` | `FallbackPolicy` |
| `state._current_delegator` re-export | `delegation_context.get_current_delegator()` |

### 3. 删除 `Supervisor` 子类
`register_hook` / `install_completion_guard` 上移至 `BaseAgent`（满足 `SupervisorProtocol`）。
Hierarchical 团队 supervisor 直接用 `BaseAgent(runtime, role_profile, max_steps=20, …)` 构造。
领域概念保留在 `SupervisorProtocol`，不在 L3 保留空壳类。

### 4. Registry 语义统一
- `ActionRegistry` / `SimpleToolRegistry` 继承 `NamedRegistry[T]`
- `ActionRegistryProtocol`：`get()` 软查询返回 `None`，`resolve()` 硬查询抛 `RegistryKeyError`
- 删除 `ComponentRegistry.resolve()`（等同 `get` 的历史别名）；调用方改用 `require()`

### 5. 文件名对齐职责
| 旧路径 | 新路径 |
|---|---|
| `layer2_runtime/hooks.py` | `event_emission.py` |
| `layer1_cognitive/team_progress/hooks.py` | `progress_hooks.py` |
| `layer2_runtime/loop_judge.py` | `default_loop_judge.py` |

### 6. 命名惯例文档化
contracts 层 `X.py` 定义 Protocol；实现层 `default_X.py` 或同名模块放默认实现
（例：`contracts/loop_judge.py` + `layer2_runtime/default_loop_judge.py`）。

### 7. 刻意不做（第四批）
`SkillRouter` 重命名为 `TemplateRouter` 涉及产品规划（是否实现 SkillRecord 检索），
留待独立 ADR。

## 后果
- 破坏性变更：`Supervisor` 类、`ComponentRegistry.resolve()`、三个过渡期别名不再导出
- `ActionRegistry.resolve()` 对未知 action_type 抛错；软查询改用 `get()`
- 新 Registry 实现应继承 `NamedRegistry` 以获得一致行为
