# ADR-0016: 契约层拆包 v3（路径即层次坐标）

## 状态
Accepted

## 背景
`lca/contracts/protocols.py` 已膨胀为 30+ Protocol 的枢纽文件，跨层类型与机制类混放，
读者无法从路径判断"这是哪一层契约"。原 `docs/contracts-agent-refactor.md`（已清理）提出了一套
完整的拆包与多 agent 补齐方案，但部分建议与本仓库既有 ADR 冲突：

| 重构文档建议 | 冲突点 | 本 ADR 决策 |
|---|---|---|
| 顶层包改名为 `cognition/`/`embodiment/` 等 | 违反 ADR-0001 五层 `layerN_*` 命名与 import-linter | **保留** `layer0_infra`…`layer4_app` |
| StepRuntime 九步顺序 think→…→perceive | 违反 ADR-0002 六步闭环 perceive→think→act→reflect→update | **保留** ADR-0002 顺序，CI 校验该顺序 |
| 新建 ADR-0015-contracts-v3 | ADR-0015 已用于"contracts 无行为类" | 本文件编号 **0016** |
| 全面禁用 `class .*Handler` | 历史实现大量 Handler 命名 | Protocol 改名；实现类同步改名；CI 拦新违规 |

## 决定

### 1. 契约层物理结构

```
lca/contracts/
├── types.py              # 跨层纯数据类型：Turn / TeamAssignment / StepOutcome
├── mechanisms.py         # 非业务机制：EventBus / Hook / HookRegistry / NamedRegistryProtocol
├── action.py             # ActionOperation + ActionRegistryProtocol（仅接口）
├── protocols/
│   ├── __init__.py       # 全量 re-export，旧 import 路径零改动
│   ├── infra.py          # L0：LLM / Tool / StateStore / Transport / Observability
│   ├── cognition.py      # L1 brain：Reasoner / Critic / BrainStrategy / …
│   ├── embodiment.py     # L1 body：Body / FallbackPolicy
│   ├── memory.py         # L1 memory：MemorySystem
│   ├── runtime.py        # L2：Runtime / StepOutcomePolicy
│   ├── agent.py          # L3：AgentEntrypoint / TeamEntrypoint
│   └── orchestration.py  # L3 团队：Orchestration* / Synthesizer / SharedMemoryStore
└── …（既有 decision/state/result 等数据文件保留）
```

### 2. 六条硬约束（可被 CI 拦截）

1. **路径即层次坐标**：`protocols/<layer>.py` 与 `layerN_*` 实现层对应
2. **签名可预测**：含 `TypedState` 的协议方法，首个非 self 参数应命名为 `state`（渐进收紧）
3. **mechanisms / types 无业务协议**：业务协议只放 `protocols/`
4. **contracts 无行为类**：具体实现放实现层（延续 ADR-0015）
5. **Loop 顺序可验证**：`CognitiveRuntime._loop` 调用序与 ADR-0002 一致
6. **共享记忆访问路径**：cognition/embodiment 不得直接 import 共享存储具体类；
   成员侧优先经 `SharedMemoryTool`（普通 Tool）访问

### 3. 命名统一

| 旧名 | 新名 | 过渡 |
|---|---|---|
| `ActionHandler` | `ActionOperation` | 保留 alias 一个周期 |
| `FallbackHandler` | `FallbackPolicy` | 保留 alias |
| `RegistryProtocol` | `NamedRegistryProtocol` | 保留 alias |

### 4. L0 子包对齐协议语义

| 旧路径 | 新路径 |
|---|---|
| `layer0_infra/registry.py` | `layer0_infra/component_registry.py` |
| `layer0_infra/tool_protocol/` | `layer0_infra/tools/` |
| `layer0_infra/state_mgmt/` | `layer0_infra/state_store/` |

旧路径保留 shim 模块 re-export，避免外部示例瞬间断裂。

### 5. 认知循环与记忆两阶段

- Loop 骨架仍为 ADR-0002：`perceive → think → act → reflect → update → judge`
- `TypedState.history` 记录 `Turn(decision, observation, reflection)`
- `MemorySystem` 增加 `perceive` / `update` 语义别名（实现可委托旧方法）

### 6. 团队协作：共享存储即 Tool

不新增 Body/Runtime 协议。组装期把绑定 `team_id` 的 `SharedMemoryTool` 注入成员
`ToolRegistry`，成员在单体循环内通过 `use_tool` 读写共享层。
既有 `MemorySystem.bind_shared_store` 路径保留（episodic 私有 / semantic 共享的 CoALA 模型）。

## 放弃的方案
- **推倒 layerN 重命名**：与 import-linter、文档、社区已形成的心智模型冲突，收益不足以覆盖成本。
- **强制九步重排 Loop**：会破坏 ADR-0002 与现有集成测试；parse/enforce 已封装在 `BrainStrategy.think` 内部。
- **SharedMemoryStore 改成全局 key-value**：丢失 CoALA 分层语义；改为 Tool 包装现有 layer API。

## 后果
- 正面：契约路径可读；CI 可拦分层/顺序/命名漂移；多 agent 共享路径清晰。
- 负面：短期存在 deprecated alias；L0 shim 增加一层间接 import。
