# ADR-0011: Simple 前缀命名约定

## 状态
Accepted

## 背景
框架中大量使用 `Simple<ProtocolName>` 命名模式（`SimpleConflictMonitor`、`SimpleTaskCoordinator`、`SimpleReasoner` 等，共 15 个类）。这个模式是团队自发形成的，但从未被显式文档化——新贡献者可能误以为 `Simple` 只是"随便起的名字"，从而在写生产级实现时命名为 `AdvancedConflictMonitor`（无信息量的比较级词），破坏命名的语义一致性。

## 决定

### `Simple` 前缀的语义契约

`Simple<ProtocolName>` 表示：该类是对应 Protocol 的**最小可行参考实现**，具备以下特征：

1. **允许简化算法**：如 `SimpleConflictMonitor.check()` 直接返回空列表，`SimpleTaskDecomposer.decompose()` 返回原始任务不分解
2. **docstring 首行必须声明能力边界**：格式为"最小实现：<一句话说明当前实现做了什么 / 不做什么>"
3. **可被替换**：生产级实现应使用领域名（如 `LLMConflictMonitor`、`EmbeddingBasedConflictMonitor`），不得使用 `Advanced` / `Pro` / `Full` 等无信息量的比较级词

### 当前已遵循此约定的类（15 个）

| 类 | 能力边界 |
|---|---|
| `SimpleConflictMonitor` | 最小实现：不检测冲突 |
| `SimpleTaskCoordinator` | 选择得分最高的候选方案 |
| `SimpleStatePredictor` | 返回候选动作描述作为预期效果 |
| `SimpleStateEvaluator` | 始终返回 1.0 |
| `SimpleTaskDecomposer` | 返回原始任务不分解 |
| `SimpleReasoner` | 调用 LLM 生成候选 |
| `SimpleDecisionParser` | JSON 提取 + action type 别名归一化 |
| `SimpleCritic` | 基于 success/failure 生成 Reflection |
| `SimpleBody` | 4 种 action_type 分发 |
| `SafeExecutor`（`SimpleSafeExecutor`） | 权限检查 + 缓存 + 重试 |
| `SimpleToolRegistry` | dict 查找 |
| `SimpleMemorySystem` | 内存级四层存储 |
| `SimpleEventBus` | asyncio.create_task pub/sub |
| `SimpleHookRegistry` | 注册 + 触发 + 可观测性 |
| `SimplePromptManager` | str.format 模板渲染 |
| `SimpleAgent` | AgentEntrypoint 默认实现：Runtime + RoleProfile + 预算透传 |
| `SimpleBrainFactory` | 默认 ModularBrain 组装工厂 |

### 禁用词补充

以下前缀/后缀在新类命名中**禁止使用**（参照 `docs/glossary.md`）：

- `Advanced`、`Pro`、`Full` — 无信息量的比较级
- `Manager`、`Util`/`Utils`、`Helper`、`Handler`、`Processor` — 泛用技术词，应使用领域名词替代
- `Data`、`Info` 作为类名后缀 — 应使用领域名词（如 `MemoryRecord` 而非 `AgentData`）

唯一已登记的豁免：`PromptManager`（`contracts/protocols.py`），理由见 `docs/glossary.md`。

## 自动化保障

| 机制 | 作用 |
|---|---|
| `tests/test_code_conventions.py::test_no_banned_class_name_patterns` | CI 红线：新类名命中禁用词正则 → 测试失败 |
| `tests/test_architecture_conformance.py` | 新类必须声明 Protocol 或登记 EXEMPT |

## 放弃的方案
- **不文档化，靠 code review 人工把关**：团队扩大后 review 标准容易漂移，显式 ADR + CI 自动化更可靠。
- **强制所有 Simple* 类必须标注 TODO 升级路径**：最小实现不等于临时实现，有些场景 Simple 就是最终选择（如 `SimpleTaskCoordinator` 的"选最高分"逻辑在单候选场景下完全够用），强制 TODO 会产生噪音。

## 后果
- 正面：新贡献者能立即理解 `Simple*` 的含义，生产级实现命名有明确指引。
- 负面：无显著负面影响。
