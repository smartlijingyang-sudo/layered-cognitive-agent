# 注册表地图（发现型 vs 运行时绑定型）

| 种类 | 注册表 | 键 | 找不到时 | 生命周期 | 注册点 |
|------|--------|----|----------|----------|--------|
| **发现型** | `ComponentRegistry` | `(category, name)` | `get`→None / `require`→raise | 全局单例 | `defaults.ensure_defaults()` |
| **发现型** | `BrainFactoryRegistry` | brain 策略名 | `resolve`→raise | 全局 | 同上 |
| **发现型** | `TeamProcessStrategyRegistry` | process 名 | `resolve`→raise | 全局 | 同上 |
| **运行时** | `ActionRegistry` | action_type | `resolve`→None | 每 Agent 一份，assembly 注入 | `action_catalog.build_default_action_registry` |
| **运行时** | `ToolRegistry` | tool name | `get`→None | 与 Action 共享同一实例 | `assemble_agent` |
| **运行时** | `TransportRegistry` | protocol_name | `resolve`→raise | 每 Agent / 团队 | `build_default_transport_registry` |
| **横切** | `HookRegistry` | event_name→多 hook | n/a | 每 Runtime | `assembly.build_hooks` |

## 硬不变量

1. **Body 与 DecisionParser 必须共享同一 `ActionRegistry` 实例。**
2. **`UseToolOperation` 闭包内的 `ToolRegistry` 必须与 `SimpleBody.tool_registry` 为同一对象**（否则 `SharedMemoryTool` 注入失效）。
3. 业务层（L0–L3）不要调用 `get_global_*` 组装对象图；只允许 L4 / 编排策略的默认工厂解析。

## 入口

- 完整对象图：`lca.layer4_app.assembly.assemble_agent`
- 默认发现注册：`lca.layer4_app.defaults.ensure_defaults`
