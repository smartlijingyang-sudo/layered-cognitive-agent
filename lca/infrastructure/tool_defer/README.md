# lca/infrastructure/tool_defer

> 状态：新建
> 所有者：@lca-maintainers
> schema_version: 1.0.0

Muse 式延迟工具加载（defer tool）的运行时实现：每 turn 只向模型注入
eager 命名空间的完整 schema，未加载的延迟命名空间只注一条目录行；
智能体通过 `tool_search(namespace="...")` 按需加载完整 schema。

来源设计：ADR-0255 §3（Muse production runtime full reference）。

## 1. 职责

- 维护 run 级 defer 会话：`ToolDeferSession`（policy + 已加载命名空间集合），
  通过 ContextVar 三件套（`set/current/reset_current_defer_session`）发布，
  仿 `lca/infrastructure/runtime_plane/capability_bindings.py` 的 tools_service 缝。
- 每 turn 在 `concept.tool.fork` dispatch 过滤/包装完成后刷新命名空间视图
  （`update_turn`：tool.name → factory 命名空间分组，turn 顺序）。
- 每 turn 向 `think.history.assemble` 投影模型可见切片：
  `render_turn()` → `(wire_specs, catalog_text)`。
- 提供加载工具本体 `ToolSearchTool`（普通 Tool，经 Tier-2 provider
  以 `"tool_search"` factory 注册，policy 强制 eager）。

## 2. 不负责

- 工具的定义与实例化（`ToolsService` / 各 Tier-2 factory）
- 每 turn 的 fork、过滤、排序与包装（`concept.tool.fork.dispatch`）
- prompt 模板与 `<tools>` XML 工具目录（`prompts.sections.tools`）
- 模型"先发现再认怂"的认知规则（prompt 侧，cognition 层）

## 3. 输入

- 每 turn 过滤后的 `Tool` 序列 + `tool.name → factory key` 映射
  （`ToolForkDispatchExecutor` 经 `ToolsService.tool_namespaces()` 提供）
- `DeferPolicy`（run 级配置：开关、eager 集合、目录文案覆写）

## 4. 输出

- 公共 API（见 `__init__.py` 显式 `__all__`）：
  `DeferPolicy` / `ToolDeferSession` / `ToolSearchTool` /
  `tool_search_factory` / ContextVar 三件套
- 每 turn：wire specs 元组（OpenAI function 形状）+ catalog 文本
  （无延迟命名空间时 catalog 为空字符串，system prompt 不变）

## 5. 允许依赖

```toml
allowed_dependencies = [
    "lca.contracts",
]
```

## 6. 禁止依赖

**pyproject.toml `[tool.lca.package_contracts."lca.infrastructure.tool_defer"].forbidden_dependencies`**:

- lca.cognition
- lca.runtime
- lca.agent
- lca.application
- lca.harness
- lca.plugins
- gateway

## 7. 副作用

- `log:emit`（预留；当前实现无日志副作用）
- ContextVar 发布/释放（run 入口 `set_current_defer_session` / `finally` 中 reset）

## 8. 失败语义

- 无 ambient session（单测、旧 run 入口）→ 调用方走 legacy 全量注入，
  不抛错、不降级。
- `load_namespace` 遇到未知命名空间 → `KeyError`（携带已知命名空间列表）；
  `ToolSearchTool.execute` 将其转为 `success=False` 的 Observation。
- `tool_search` 参数非法 → `validate` 返回错误字符串（不抛错）。
- policy `enabled=False` → 每 turn 全量注入（与旧行为逐字节一致）。

## 9. 公共入口

**__init__.py 显式 __all__**:

- `DeferPolicy`
- `ToolDeferSession`
- `ToolSearchTool`
- `tool_search_factory`
- `current_defer_session`
- `set_current_defer_session`
- `reset_current_defer_session`
