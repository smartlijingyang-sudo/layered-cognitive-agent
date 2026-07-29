# ADR-0017: 禁止裸字符串字面量与裸 Any 类型标注

## 状态

Accepted

## 背景

代码审查中发现两类反复出现的弱类型问题：

1. **裸字符串字面量充当枚举值**：`action_type == "respond"`、`policy_name = "roster_coverage"`、`status == "completed"` 等散落在 20+ 个文件中。拼写错误无法被编译器捕获，重构时只能全局文本搜索，遗漏即产生静默 bug。

2. **`Any` 类型标注泛滥**：`agent_card: Any`、`state: Any`、`members: list[Any]` 等绕过 mypy 检查，使类型系统形同虚设。新贡献者无法从签名理解接口契约。

## 决定

### 1. 领域枚举集中定义

所有具有有限值域的领域字符串统一收敛到 `lca/contracts/enums.py`，使用 `str` 继承的 `Enum`：

```python
class ActionType(str, Enum):
    RESPOND = "respond"
    USE_TOOL = "use_tool"
    DELEGATE = "delegate"
    HANDOFF = "handoff"
```

**为什么用 `str` Enum 而不是 `Literal`？**

- `Literal` 是类型别名，不提供运行时值（无法 `Literal.RESPOND`）
- `str` Enum 兼容字符串比较（`ActionType.RESPOND == "respond"` 为 `True`），序列化无损
- 枚举成员可被 `for` 遍历、`in` 检测、IDE 自动补全

**已定义的枚举：**

| 枚举 | 值域 | 替代的裸字符串 |
|------|------|---------------|
| `ActionType` | respond, use_tool, delegate, handoff | `action_type == "respond"` |
| `TaskStatus` | submitted, working, completed, failed... | `status == "completed"` |
| `TeamProcess` | hierarchical, sequential, parallel... | `process: "hierarchical"` |
| `HookEvent` | on_start, pre_think, post_act... | `event_name == "post_act"` |
| `SpanStatus` | ok, error | `span.status = "error"` |
| `SnapshotReason` | periodic, pre_approval, manual, on_error | `reason="periodic"` |
| `ReflectionVerdict` | on_track, needs_correction... | `verdict == "on_track"` |
| `SharedMemoryOp` | read, write, list | `op == "read"` |
| `CompletionPolicyName` | roster_coverage, none | `policy_name = "roster_coverage"` |
| `DelegationProtocol` | internal, a2a, mcp | `protocol: "internal"` |
| `ContentType` | text, image, audio, structured | `content_type = "text"` |
| `MessageKind` | text, data, file | `kind: "text"` |
| `MessageRole` | user, agent | `role: "user"` |
| `RoleStatus` | pending, in_progress, done, failed | `status == "done"` |
| `NodeType` | entry, exit, agent, router, aggregator | `type="entry"` |
| `EdgeType` | fixed, conditional, parallel | `type="conditional"` |

### 2. Any 类型标注管控

**禁止模式（pre-commit 阻断）：**

```python
agent_card: Any  # ❌ 应用 AgentCard | str
state: Any  # ❌ 应用 TypedState
members: list[Any]  # ❌ 应用具体类型或添加注释说明
hook_fn: Any  # ❌ 应用 Hook / Callable
```

**允许模式（白名单）：**

```python
dict[str, Any]           # ✅ 开放 schema 容器（extra, attributes, arguments）
**kwargs: Any            # ✅ Protocol / hook 可变关键字参数
payload: Any             # ✅ 通用载荷（Observation, Event, TeamMessage）
```

**允许文件（整体豁免）：**

- `lca/contracts/types.py` — 跨层通用类型定义
- `lca/contracts/mechanisms.py` — 跨层机制协议
- `lca/contracts/protocols/*` — Protocol 定义（结构性多态需要）

### 3. 提交时自动校验

两个 pre-commit hook 在 `git commit` 时自动运行：

- `scripts/check_no_any.py` — 扫描 `Any` 使用，白名单外即阻断
- `scripts/check_no_bare_strings.py` — 扫描 `== "domain_string"` 模式，提示对应枚举

## 自动化保障

| 机制 | 作用 |
|------|------|
| `scripts/check_no_any.py` | pre-commit 阻断裸 Any |
| `scripts/check_no_bare_strings.py` | pre-commit 阻断裸字符串比较 |
| `mypy` | 类型正确性（str Enum 与 str 兼容） |
| `ruff` | import 排序、未使用导入 |

## 迁移指南

### 新增枚举值

1. 在 `lca/contracts/enums.py` 的对应枚举中添加成员
2. 所有比较/赋值站点使用枚举常量
3. 如果是新枚举类型，更新 `check_no_bare_strings.py` 的 `_DOMAIN_STRINGS`

### 消除 Any

```python
# Before
def send_task(self, agent_card: Any, ...) -> str: ...

# After
def send_task(self, agent_card: AgentCard | str, ...) -> str: ...
```

如果确实无法避免 `Any`（如第三方 SDK 类型、动态注册表），在行尾添加注释说明原因，并将文件加入 `_FILE_ALLOWLIST` 或在行级白名单中添加模式。
