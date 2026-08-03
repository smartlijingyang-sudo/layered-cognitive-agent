# ADR-0026: Supervisor 一等公民 — ConsultationState + SupervisorReasoner

## 状态
Accepted

## 背景

hierarchical 模式的产品前提是：**supervisor IS an agent that reasons about
delegation**——在合法 waiting 集合内，由 LLM 决定下一个问谁、怎么问；
`MustConsultAllMembers` 负责不变量与单候选短路（见其 docstring 中的
"genuine LLM discretion"）。

实现却把这一前提压扁成：

```
通用 CognitiveAgent + RunContext 扁平 team 字段 + RoleMode 分支 + gate 夹具
```

症状包括：

1. `RunContext` / `AgentState` 混放调用元数据与团队协调状态
2. `SimpleReasoner` 用 `if role_mode != SOLO` 兼职 supervisor 选人认知
3. 每加一个 team 参数就沿 `TeamConfig → TeamContext → RunContext → AgentState` 复制一层
4. L1 通用认知组件被 team 协议穿透

ADR-0001 曾把 `Supervisor` 列为 L3 典型内容，但对象图里没有一等组合边界。

## 决定

### 1. 控制面类型：`ConsultationState`

```python
@dataclass
class ConsultationState:
    member_status: MemberStatus
    teammates: list[RoleProfile]
    delegate_max_attempts: int = 3
    delegate_attempts: dict[str, int] = field(default_factory=dict)
```

- 仅 hierarchical supervisor 会话存在；solo / member 为 `None`
- board 与 retry 计数是循环内可变状态；teammates / max_attempts 会话内固定
- **不是** 通用调用元数据的一部分（与 `trace_id` / `deadline` 生命周期不同）

### 2. 干净的 `RunContext` / `AgentState`

| 字段 | 含义 |
|---|---|
| `trace_id` / `from_role` / `deadline` / `context_refs` | 调用元数据 |
| `consultation: ConsultationState \| None` | 可选的 supervisor 控制面引用 |

删除：`role_mode`、`teammates`、`member_status`、`delegate_max_attempts`、
`delegate_attempts` 在通用容器上的扁平字段。删除 `RoleMode` 枚举。

### 3. 组件边界：`SimpleReasoner` vs `SupervisorReasoner`

| 组件 | 职责 |
|---|---|
| `SimpleReasoner` | team-agnostic；只服务 solo / member；只用 `react_prompt` |
| `SupervisorReasoner` | 固定 `hierarchical_prompt`；要求 `state.consultation`；有界 LLM 选人/措辞 |
| `MustConsultAllMembers` | 读 `state.consultation.member_status`；单候选短路 + 结算不变量 |

### 4. 组装期绑定（对齐 ADR-0001 的 Supervisor 位）

`TeamOrchestrator._bind_supervisor` 在组合期完成：

1. channel → body
2. decision gate → brain
3. `SimpleReasoner` → `SupervisorReasoner.from_simple(...)`（身份在组装期成型）

`HierarchicalStrategy` 在运行时只注入：

```python
RunContext(consultation=ConsultationState(member_status=..., teammates=..., ...))
```

差异**不在**每次 `think()` 用 `RoleMode` 发现身份。

## 放弃的方案

- **仅嵌套 TeamCoordination 命名空间**（方案 A）：字段更干净，但不拆
  `SimpleReasoner` 双身份——仍是补丁。
- **编排层纯 selector（对齐 AutoGen GroupChatManager）**：推翻
  "supervisor 推理委派"的产品前提，改动量与语义是另一条产品线。
- **ContextVar 承载全部 team 状态**：依赖隐式、resume 困难；`from_role`
  的 ContextVar 仅用于跨 `asyncio.create_task` 边界（ADR-0017 范围）。

## 后果

- **正面**：
  - 通用 Agent 路径零 team 协议知识
  - supervisor 控制面在类型与组装上可见
  - 保留有界 LLM discretion + gate 护栏
  - 新增 team 字段只改 `ConsultationState`，不污染 `SimpleReasoner`
- **负面 / 迁移**：
  - 测试与外部若构造扁平 `member_status=` / `role_mode=` 需改为
    `consultation=ConsultationState(...)`
  - 自定义 Brain 必须满足 `HasReplaceableReasoner`（暴露 `reasoner`），
    或组装前自行装好 `SupervisorReasoner`；失败时 `SupervisorBindError` 显式抛出

## 补充：防埋坑加固（同 ADR 修订）

### 5. 控制面字段白名单（防垃圾袋复发）

`ConsultationState` **仅** hierarchical 结算协议。字段集合锁在：

```python
CONSULTATION_FIELD_WHITELIST = {
    "member_status",
    "teammates",
    "delegate_max_attempts",
    "delegate_attempts",
}
```

- 类型名：`ConsultationState`（无过渡别名）
- CI：`assert_consultation_field_whitelist()` + `tests/test_supervisor_bind.py`
- **禁止**把 debate / handoff / group-chat / graph cursor 塞进该类型；
  那些属于对应 `TeamProcessStrategy` 的 strategy-local state 或独立 Session 类型

加字段流程：改 dataclass → 同步白名单 → 更新本 ADR → 说明为何属于 hierarchical 结算。

### 6. `SupervisorBinder`（防 isinstance 静默绑定）

组装期唯一入口：`lca/layer3_agent/supervisor_bind.py`

```text
SupervisorBinder.bind(supervisor, transport=..., policy=...)
  ├─ runtime 必须 HasBrainBodyMemory，否则 SupervisorBindError
  ├─ transport 非空 → body 必须 HasChannel
  ├─ policy 非空 → brain 必须 SupportsDecisionGate
  └─ brain 必须 HasReplaceableReasoner → cognition_factory(reasoner)
```

- 默认 `cognition_factory`：`SimpleReasoner` → `SupervisorReasoner`；
  已是 `SupervisorReasoner` 则恒等；其它类型 **raise**（不静默跳过）
- 可注入自定义 `cognition_factory` 以扩展 supervisor 认知实现
- `TeamOrchestrator` 接受可选 `supervisor_binder=`，默认 `SupervisorBinder()`
- `SimpleReasoner` AST 门禁：类体内不得出现 team 控制面符号

### 7. 扩展其它 team 体制时的纪律

| 体制 | 状态放哪 | 不要放哪 |
|---|---|---|
| hierarchical 结算 | `ConsultationState` | — |
| sequential/parallel/handoff | strategy + `invoke_member`（agent 无 consultation） | ConsultationState |
| debate / group chat / graph | 专用 Session 或 strategy-local | ConsultationState / SimpleReasoner |

## 与既有 ADR 的关系

- **ADR-0001**：兑现 L3 `Supervisor` 组合位（`SupervisorBinder` 组装期绑定）
- **ADR-0002**：认知环不变；consultation 只是 `AgentState` 上的可选会话
- **ADR-0006**：hierarchical strategy 仍是 supervisor-only 入口
- **ADR-0025**：`delegate_max_attempts` 管道改为
  `TeamConfig → TeamContext → ConsultationState`（经 `RunContext.consultation`）
