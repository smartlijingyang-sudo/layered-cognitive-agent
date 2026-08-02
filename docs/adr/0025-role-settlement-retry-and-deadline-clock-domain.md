# ADR-0025: 角色结算状态、委派重试与 deadline 时钟域

## 状态

Accepted

## 背景

层次团队（hierarchical team）的 Supervisor 通过 `MustConsultAllMembers` 决策门强制咨询所有必需角色后再回应。该状态机存在四个根因问题：

1. **settled/done 混淆（问题 A）**：`MemberStatus` 只有一根轴——"是不是 DONE"。`waiting_roles()` 返回所有非 DONE 角色（含 FAILED），导致已 FAILED 的角色被反复委派直到 Budget 耗尽。根因是缺少"已尝试完（settled）"与"成功（done）"的区分。

2. **时钟域混用（问题 B）**：`DelegateOperation.execute()` 用 `spec.deadline.timestamp()`（POSIX wall-clock）减 `asyncio.get_running_loop().time()`（monotonic, 任意 epoch），结果无意义，`deadline` 字段实际不生效。

3. **gate 单向兜底（问题 C）**：`MustConsultAllMembers.enforce()` 只拦截 `RESPOND`。LLM 主动 `DELEGATE` 给已 DONE 或终态 FAILED 的角色时直接放行，造成重复委派。

4. **消费顺序不确定（问题 D）**：`InMemoryMemberStatus.required_roles` 是 `frozenset[str]`，迭代顺序在不同 `PYTHONHASHSEED` 下不同。`waiting_roles()[0]` 选出的"下一个委派角色"不可复现。

此外，`_wait_for_result` 的 poll 回退分支是死代码（所有 transport 都实现 `wait_result`），且为 `A2ATransport.wait_result` 正确逻辑的反转副本。

## 决定

### 1. settled/done 分类收敛到单一函数

新建 `lca/contracts/role_status_rules.py`，定义 `is_terminal_status()` 和 `is_success_status()` 两个纯函数。任何需要判断 RoleStatus 是否终态 / 是否成功终态的地方，一律引用本文件，禁止在别处用 `== RoleStatus.DONE` 重新发明判定逻辑。

`MemberStatus` Protocol 新增 `all_settled() -> bool`：所有必需角色的状态都是终态（DONE 或 FAILED）。`waiting_roles()` 改为返回 `not is_terminal_status` 的角色——FAILED 角色不再出现在 waiting 列表中。

### 2. wall-clock 专用时间工具

在 `lca/contracts/ids.py` 新增 `remaining_seconds(deadline, *, now=None) -> float` 和 `elapsed_seconds(started_at, *, now=None) -> float`。参数类型是 `datetime`（不是 `float`），在类型检查层面拒绝 monotonic clock 混入。

`DelegateOperation.execute()` 用 `remaining_seconds(spec.deadline)` 替代 `spec.deadline.timestamp() - asyncio.get_running_loop().time()`。deadline 已过期时提前短路返回超时 Observation。

### 3. gate 裁决收敛到单一纯函数

新建 `lca/layer1_cognitive/member_status/policy.py`，定义 `compute_required_action(board) -> RequiredAction`。gate 的两个方向（阻止提前 RESPOND + 阻止重复 DELEGATE 到已终态角色 + 全部结算后将 DELEGATE 改写为 RESPOND）共享同一个函数调用。

gate 管辖范围限定为 `RESPOND` 和 `DELEGATE`，`HANDOFF`/`USE_TOOL` 不在本次管辖范围（out-of-scope）。

### 4. required_roles 消费顺序确定性

`InMemoryMemberStatus` 内部改用 `role_order: tuple[str, ...]` 保证迭代顺序确定性。Protocol 暴露的 `required_roles` 属性签名不变（仍返回 `frozenset[str]`）。

### 5. 重试逻辑保留在 tracking.py，不上 Board Protocol

重试逻辑留在 `update_member_status()`（tracking.py），从 `AgentState.delegate_max_attempts` 读取上限，从 `AgentState.delegate_attempts` 读取已尝试次数。Board 保持 dumb 容器，不知道 failure_kind / max_attempts。

`delegate_max_attempts` 通过 `TeamConfig → TeamContext → RunContext → AgentState` 既有管道传递，与 `member_status`、`teammates`、`role_mode` 走同一条路。不复用 `RetryPolicy`（其 `backoff_base_s`/`backoff_multiplier` 对 delegate 无意义）。

### 6. delegate 失败路径统一产出 failure_kind

- timeout → `FAILURE_KIND_TRANSIENT`（由 `_wait_for_result` 标注）
- agent-not-found（InternalTransport）→ `FAILURE_KIND_VALIDATION`（由 transport 层 `_fail_observation` 标注）
- member 执行失败 → `FAILURE_KIND_EXECUTION`（默认 fallback，Critic 自动归类）

### 7. 删除 poll 回退分支

`_wait_for_result` 收敛为直接调用 `transport.wait_result` + `except TimeoutError`。删除反转的 poll 回退分支和 `_POLL_INTERVAL_S` 常量。

### 8. as_prompt_text 诚实暴露永久失败

新增第三档文案：当 `all_settled()` 为真但存在 FAILED 角色时，提示"X 角色多次尝试后仍不可用，本次结论不含该视角"。这是刻意的降级行为（degradation by design）。

## 后果

### 正面

- 四个根因各自收敛到单一事实来源，不会在新代码中复发。
- 委派状态机变为完全确定性、有界、可测试的。
- `deadline` 字段真正生效。
- delegate 失败路径统一产出 failure_kind，Critic 可正确区分而不是全部落入默认值。
- `required_roles` 消费顺序可复现。

### 代价

- `MemberStatus` Protocol 从 6 方法增至 7（+`all_settled`），向后兼容。第三方 `MemberStatus` 实现需要补 `all_settled()`。
- `TeamConfig`/`RunContext`/`AgentState` 各新增一个带默认值的字段，向后兼容。
- `InMemoryMemberStatus` 构造参数从 `required_roles: frozenset` 改为 `role_order: tuple`（Protocol 签名不变，实现变了）。第三方若直接构造 `InMemoryMemberStatus` 需更新参数名。
- `delegate_max_attempts` 默认值 3 是业务判断，不是纯技术决定。
