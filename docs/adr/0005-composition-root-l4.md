# ADR-0005: L4 组合根模式

## 状态
Accepted

## 背景
严格分层后，"谁来创建并组装所有具体对象"成了一个问题——如果每层只知道下一层的 Protocol，那具体实现类的实例化必须由某个地方统一完成。

## 决定
L4 是**唯一允许 import 所有具体类的组装根**（Composition Root），内部三个文件职责分离：

1. **`layer4_app/defaults.py`**：纯发现型组件注册（`ensure_defaults` / `register_defaults`）——把框架内置默认实现注册进 `ComponentRegistry` / 策略注册表，使 `Agent(...)` 可以通过名字字符串选择实现（如 `memory="simple"`），并允许用户在调用 Agent 之前注册自己的实现。不含对象图构造。
2. **`layer4_app/assembly.py`**：唯一对象图工厂——Agent / Team 共享组装管线、transport/team 构建都在这里完成。
3. **`layer4_app/api.py`**：开发者唯一接触的薄门面——`Agent(role, goal, backstory, tools, llm)` 三行创建 Agent，委托 assembly 完成 L0-L3 全部对象的 DI 组装。

**约束**：L0-L3 不得反向依赖 L4（由 import-linter `forbidden` 契约保证）。

## 放弃的方案
- **每层各自实例化**：会导致循环依赖或需要复杂的延迟注入。
- **全局 ServiceLocator**：隐式依赖，测试时难以替换。显式构造 + 注册表模式更可控。

## 后果
- 正面：开发者体验极简（三行代码）；替换任何组件只需"注册新实现 + 传名字字符串"。
- 负面：L4 组装根需要 import 所有层的具体类，随着框架增长会变长——按"注册 / 组装 / 门面"三职责拆文件控制规模。
