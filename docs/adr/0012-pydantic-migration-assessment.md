# ADR-0012: contracts 层维持 dataclass，不迁移到 Pydantic

## 状态
Accepted

## 背景
项目早期设计文档曾提出 "Pydantic v2 + Protocol"，`pyproject.toml` 的 `[tool.mypy]` 中也留了一行注释 `# contracts 迁移到 pydantic.BaseModel 之后打开下面这行`。但截至目前，`lca/contracts/` 下的 27 个数据模型全部使用 stdlib `@dataclass`，没有任何 Pydantic 依赖。

这构成了"规范与代码的漂移"——新贡献者可能误以为 dataclass 是临时方案。需要显式记录决策。

## 决定

**维持 `@dataclass`，不迁移到 `pydantic.BaseModel`。**

理由：

1. **contracts 层是纯数据容器，不需要 Pydantic 的运行时验证**。所有字段类型已由 mypy 在静态检查阶段保障（`disallow_untyped_defs = true`），运行时再验一遍是冗余的。
2. **LCA 是框架不是应用**。Pydantic 的核心价值在系统边界（HTTP API 入口/出口的序列化与验证），但 LCA 的 contracts 层只在框架内部流转，边界验证应由使用方（宿主应用）决定。
3. **迁移成本高、收益低**。27 个 dataclass 全部改为 BaseModel 需要：处理 `field(default_factory=...)` 到 `Field(default_factory=...)` 的映射、Literal 类型的兼容性、`@dataclass` 特有的 `__post_init__` 模式（如 `TeamSharedMemoryStore` 的 frozenset 校验）、以及所有测试中直接构造 dataclass 的代码。这些工作量换来的只是"与定位文档一致"——而正确的做法是更新定位文档。
4. **Pydantic 依赖应保持可选**。当前 LCA 的运行时依赖只有 `httpx`（A2A 传输），如果把 Pydantic 变成核心依赖，会加重框架的安装体积和启动时间，违背"轻量框架"定位。

### 后续行动

- ~~更新早期设计文档~~（文档已清理删除）
- 移除 `pyproject.toml` 中注释掉的 `pydantic.mypy` 插件行，避免误导
- `pyproject.toml` 的 `[tool.mypy]` 中 `pydantic>=2.9` 保留在 `typecheck` 依赖组（用于 `isinstance` 类型推断的辅助，不影响运行时）

## 自动化保障

| 机制 | 作用 |
|---|---|
| `uv run lint-imports` | 契约 3 确保 contracts 不依赖实现层，间接防止 Pydantic 验证逻辑泄漏 |
| `uv run mypy lca` | 静态类型检查覆盖所有 dataclass 字段，替代 Pydantic 的运行时验证 |

## 放弃的方案
- **全量迁移到 Pydantic BaseModel**：工作量大（27 个模型 + 所有测试），收益仅限于"与定位文档一致"，而定位文档本身可以更新。
- **混合模式（部分 Pydantic + 部分 dataclass）**：增加认知负担，贡献者需要判断"这个模型该用哪个"，不如统一一种。
- **引入 Pydantic 但仅用于边界 DTO（如 AgentCard）**：当前 AgentCard 只在跨进程传输时使用，序列化由传输层（A2A/MCP）自行处理，不需要框架层介入。

## 后果
- 正面：零迁移成本，运行时依赖保持最小化，团队不需要学习 Pydantic 的 Field/validator 模式。
- 负面：如果未来 LCA 需要直接暴露 HTTP API（如 Agent 即服务），使用方需要自行添加 Pydantic 或其他序列化层——但这正是"框架不管应用层边界"的设计意图。
