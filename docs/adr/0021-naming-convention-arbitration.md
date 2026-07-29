# ADR-0021: Simple / Default / 领域名命名仲裁与 L3 Agent 改名

## 状态
Accepted  
Relates-to: ADR-0011, ADR-0019

## 背景
ADR-0011 登记了 15 个 `Simple<Protocol>` 类；ADR-0019 §6 又约定 L2 实现层使用 `Default<X>` 文件名。
两套规则并行、互不知晓。同时 L3 的 `BaseAgent` 听起来像抽象基类，实际是 `AgentEntrypoint` 的唯一默认实现，
既不符合 Simple* 也不符合 Default*。

## 决定

### 命名三分规则

| 层级 | 前缀/风格 | 示例 |
|---|---|---|
| L1 认知组件（Brain/Body/Memory 内部模块） | `Simple<Protocol>` | `SimpleReasoner`, `SimpleBrainFactory` |
| L2 运行时策略（LoopJudge/StepOutcomePolicy 等编排级默认） | `Default<Protocol>` 或 `default_*.py` | `DefaultLoopJudge`, `DefaultStepOutcomePolicy` |
| L3 Agent/Team 抽象 | 优先有信息量的领域名；无法命名时退回 `Simple<Protocol>` | `SimpleAgent`, `TeamOrchestrator` |

### L3 改名

- `BaseAgent` → `SimpleAgent`（`lca/layer3_agent/simple_agent.py`）
- 保留 `BaseAgent = SimpleAgent` 过渡期别名一个发布周期

### 组合根边界（与 ADR-0018 对齐）

- `assembly.py`：唯一对象图工厂，含 transport/team 构建与 supervisor 预算 floor
- `defaults.py`：纯 `register_defaults()` / `ensure_defaults()`，不含对象构造
- `api.py`：薄门面，不做 supervisor 预算调整

### Runtime 能力协议

- `ExposesComponents` / `HookRegistryHolder`（`contracts/protocols/capabilities.py`）
- L3 通过 `isinstance` 探测，禁止裸 `getattr(runtime, "body")`

### BrainFactory 正式协议

- `BrainFactory` Protocol 定义于 `contracts/protocols/cognition.py`
- `SimpleBrainFactory` 位于 `lca/layer1_cognitive/brain/default_factory.py`

## 后果
- 破坏性变更：`from lca.layer3_agent import BaseAgent` 仍可用（alias），但新代码应使用 `SimpleAgent`
- 删除 `lca/layer4_app/brain_factory.py`（环消除，非绕环）
- CI 护栏见 `tests/test_refactor_guards.py`、`tests/test_layer_boundary.py`
