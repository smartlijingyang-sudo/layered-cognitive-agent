# MCP 集成与工具策略管道重构设计方案

- **日期**：2026-09-22
- **状态**：Approved
- **自治等级**：`DRAFT` (AP-05)
- **关联 Commit**：`7ded653eb392e3b6c9120e44d87b193e0ff052b2`

---

## 1. 背景与根因剖析

在 commit `7ded653eb` 引入 AWS MCP 工具时，为了快速打通链路，引入了多处违背 LCA 架构规范的临时逻辑与坏味道：

1. **暗度陈仓的工厂注册耦合**：
   在 [`lca/plugins/act/tools/provider.py`](file:///home/lichao/layered-cognitive-agent/lca/plugins/act/tools/provider.py) 中，`Config.factories` 默认声明为 `["g2a"]`，但注册逻辑却在 `if "g2a"` 中顺带注册了 `mcp` 工厂。配置未显式声明，违背单一真值（SSOT）与单一职责原则。
2. **策略过滤硬编码与安全鉴权漏检（C5 衰减破坏）**：
   在 [`lca/infrastructure/tools/assistant/filter.py`](file:///home/lichao/layered-cognitive-agent/lca/infrastructure/tools/assistant/filter.py) 中，直接对 `mcp__` 前缀进行多段字符串切分，且通过单独的 `continue` 完全跳过了后方的 `_required_grant(tool)` 校验，导致 MCP 工具一旦声明了权限要求却能特权穿透。
3. **假单元测试破坏确定性（C8 不变量违背）**：
   在 [`tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py`](file:///home/lichao/layered-cognitive-agent/tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py) 中，放在 `unit/` 目录下的测试依赖外部网络、`uvx` 下载数十 MB 依赖、真实 AWS 凭证与端点，导致单测耗时长达 50s 且因外部环境失败。

---

## 2. 架构边界（AP-01）

### 2.1 Owns（负责范围）
1. [`bundles/base.yaml`](file:///home/lichao/layered-cognitive-agent/bundles/base.yaml)：显式补齐 `lca-tools-provider` 的 `factories: [g2a, mcp]` 配置，确立配置 SSOT；
2. [`lca/plugins/act/tools/provider.py`](file:///home/lichao/layered-cognitive-agent/lca/plugins/act/tools/provider.py)：消除分支硬编码，重构为表驱动工厂注册；
3. [`lca/infrastructure/tools/assistant/filter.py`](file:///home/lichao/layered-cognitive-agent/lca/infrastructure/tools/assistant/filter.py)：抽取纯函数 `_tool_matching_names`，重构为统一的 Deny $\rightarrow$ Grant $\rightarrow$ Allow 漏斗过滤管道，补齐 MCP 工具的 `required_grant` 校验；
4. [`tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py`](file:///home/lichao/layered-cognitive-agent/tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py)：消除外部网络与真实 AWS 凭证依赖，使用 Stub/Mock MCP Manager 重构为离线确定性单元测试；
5. [`tests/plugins/assistant/test_filter_tools.py`](file:///home/lichao/layered-cognitive-agent/tests/plugins/assistant/test_filter_tools.py)：增补 MCP 工具带 `required_grant` 时的拒绝与放行测试用例。

### 2.2 Does NOT own（严格负边界）
1. 严禁修改 [`lca/infrastructure/mcp/manager.py`](file:///home/lichao/layered-cognitive-agent/lca/infrastructure/mcp/manager.py) 底层通信传输状态机；
2. 严禁修改外部工作区的 `.lca/mcp.yaml` 文件与宿主机 AWS 凭据；
3. 严禁改动 `contracts/` 层的任何基本 Protocol 签名；
4. 严禁引入任何新的第三方外部依赖。

---

## 3. 详细组件设计与模式应用

### 3.1 表驱动工具工厂注册 (`provider.py`)
```python
_TOOL_FACTORIES: dict[str, Callable[[object], list[Tool]]] = {
    "g2a": _g2a_factory,
    "mcp": _mcp_factory,
}

class Config(BaseModel):
    model_config = {"extra": "forbid"}
    factories: list[str] = Field(default_factory=lambda: ["g2a", "mcp"])

async def setup(ctx: PluginContext, config: Config) -> None:
    tools_seam = ctx.require("tools")
    for name in config.factories:
        factory = _TOOL_FACTORIES.get(name)
        if factory is not None:
            tools_seam.register_factory(name, factory)
```
- **单一真值**：[`bundles/base.yaml`](file:///home/lichao/layered-cognitive-agent/bundles/base.yaml) 中显式声明 `factories: [g2a, mcp]`。
- **开闭原则（OCP）**：新增工厂仅需在字典表追加映射。

### 3.2 标识符解析器与统一过滤管道 (`filter.py`)
```python
def _tool_matching_names(tool: Tool) -> frozenset[str]:
    """提取工具的所有有效匹配键（完整全称、短别名、协议类别、Server 命名空间）"""
    name = tool.name
    keys: set[str] = {name}
    if name.startswith("local_"):
        keys.add(name[6:])
    elif name.startswith("mcp__"):
        parts = name.split("__", 2)
        keys.add("mcp")
        if len(parts) > 1 and parts[1]:
            keys.add(parts[1])
        if len(parts) > 2 and parts[2]:
            keys.add(parts[2])
    return frozenset(keys)

def filter_tools_by_assistant(tools: Iterable[Tool], home_path: str | Path) -> _ToolSet:
    home = Path(home_path)
    policy = _load_tools_policy(home)
    if policy is None:
        return ()
    allow, deny = policy
    grants = _load_grants(home)

    kept: list[Tool] = []
    for tool in tools:
        keys = _tool_matching_names(tool)
        # 1. Deny 拦截（最高优先级）
        if bool(keys & deny):
            continue
        # 2. Grant 鉴权防线（C5：覆盖 required_grant）
        required_grant = _required_grant(tool)
        if required_grant and required_grant not in grants:
            continue
        # 3. Allow 放行检查
        if not allow or bool(keys & allow):
            kept.append(tool)
    return tuple(kept)
```

---

## 4. 测试断言与架构不变量矩阵（AP-02）

| 不变量 | 规范要求 | 验证断言 |
|---|---|---|
| **C5 (能力衰减)** | 凡声明 `required_grant` 的工具必须严格受 `grants.yaml` 约束，无特权穿透 | 在 `tests/plugins/assistant/test_filter_tools.py` 中，断言带有 `required_grant="aws.read"` 的 MCP 工具在无 grant 时拒绝，有 grant 时放行。 |
| **C8 (确定性)** | 单元测试必须自包含、离线可运行、毫秒级响应，禁止隐式依赖网络与外部凭证 | 重构 `tests/unit/infrastructure/mcp/test_aws_mcp_dialogue.py` 为 Mock 架构，执行耗时 < 2s，脱网 100% 通过。 |
| **OCP (工厂开闭)** | 工具工厂按配置严格按需注册，无隐式绑定与副作用穿透 | 验证配置不同 `factories` 列表时仅注册对应的工厂。 |

---

## 5. 异常处理与边界

1. **畸形 MCP 工具命名**：`_tool_matching_names` 进行边界保护，即使出现非标准命名也不崩溃，安全降级为 `{name}`。
2. **Deny 终极优先**：集合运算 `keys & deny` 优先检查，即使 allow 包含通配词也坚决拦截。
3. **Fail-closed**：缺少策略配置时一律返回空元组，杜绝默认放行越权。
