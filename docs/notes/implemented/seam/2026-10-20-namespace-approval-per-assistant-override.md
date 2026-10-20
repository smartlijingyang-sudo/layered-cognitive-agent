# Agent Note: 命名空间审批策略可按助理覆盖（profile_runtime.namespace_approval）

Status: implemented

## Problem

run_b4fa9114c6a0 每次调用 shell 命令（runCommand）都暂停等人批准。原因是
`DeferPolicy.namespace_approval` 默认把 `shell` 设为 `require_approval`，且没有 per-assistant
覆盖入口。用户期望自己的默认助理执行 shell 命令时不再每次被问。这是审批 seam 的配置面缺口，
不是 bug：ADR-0256/ADR-0292 的 fail-closed 默认保持不变。

## Decision

`profile.json.runtime` 新增可选键 `namespace_approval`，值是 `namespace -> approval level`
的映射（如 `{"shell": "allow"}`）。`AssistantSpec.__post_init__` 校验它必须是 `Mapping[str, str]`，
非 dict 或键值非字符串在 resolve 期抛 `ValueError`（fail-closed）。

`new_defer_session` 接受 `namespace_approval` 参数，用
`dataclasses.replace(policy, namespace_approval={**默认, **覆盖})` 合并进
`DeferPolicy.namespace_approval`。create-run 路径从 `spec.profile_runtime` 读取该键并传入。
暂停时 `_capture_namespace_approval()` 捕获当前 defer session 生效的 `namespace_approval`，
存进 `RunSession.namespace_approval` 并随 resume bundle 持久化（`_BUNDLE_FIELDS` 新字段，
`validate_bundle` 对非 dict 判 corrupt）；resume 路径恢复同一策略。

`NamespaceApprovalStrategy` 已读 `policy.namespace_approval`，值非 `require_approval` 即放行，
审批引擎无需改动。全局默认保持 fail-closed（`shell=require_approval`），只有显式配置的助理
可以放宽。

## Alternatives considered

### Why not 改全局默认 `DEFAULT_NAMESPACE_APPROVAL` 去掉 shell？

一行改动，但所有助理都失去 shell 审批保护。代价是全局安全姿态变弱，且与 ADR-0256/0292 的
fail-closed 默认冲突。未来任何助理的误操作都直接执行。

### Why not 保持策略不变，只处理单次 run？

用 `lca-ops runs answer` 批准当次 run 能完成当前任务，但不消除“总需要批准”的诉求。代价是每次
shell 调用都要人工介入。

### Why not 用 `plan.yaml` overlay 承载？

`PlanOverlay` 只有 `prompt` / `graph` 覆盖且 `extra="forbid"`，需要扩 schema。审批是运行参数，
归 `profile.json.runtime`（ADR-0242 D9 / ADR-0248 既有透传通道）更贴切，且不新开配置面。

## Consequences

配置了 `namespace_approval: {"shell": "allow"}` 的助理，新 run 调用 shell 命令不再暂停、
直接执行。未配置的助理保持 `shell=require_approval` 不变。resume bundle 增加可选字段，
旧 bundle 缺省允许，不破坏既有暂停 run。

放宽 shell 审批会降低该助理的防误操作保护。这是显式配置行为，默认不变；配置时需知晓
`DEFAULT_NAMESPACE_DESCRIPTIONS` 中 shell 的“危险操作会先请示你”说明与该助理实际行为不一致。

## Verification

`tests/contracts/models/assistant/test_spec.py` 覆盖 `namespace_approval` 的合法/非法配置校验。
`tests/infrastructure/runtime_plane/test_namespace_approval_strategy.py` 覆盖 override 放行
shell 工具与默认策略保持 require_approval。
`tests/plugins/transport/webserver/test_run_restart_recovery.py` 覆盖 resume bundle 对
`namespace_approval` 的 round-trip 与错类型拒绝。

实跑验证：默认助理配置 override 后，run `run_9be7126ac259`（“请在沙箱里运行 echo
hello-lca-approval-test”）completed，三次 `act.authorize` 均 `approval_required=false`，
`runCommand` 输出 `hello-lca-approval-test`，未暂停。

## Related

- [ADR-0256](../../../adr/0256-tool-namespace-taxonomy.md) 工具命名空间分类与 `namespace_approval`
- [ADR-0292](../../../adr/0292-authorization-semantic-isolation.md) 授权语义隔离，`act.authorize` 以策略信号为准
- [ADR-0242](../../../adr/0242-assistant-creation-home-runtime.md) Home 数据与 `profile.json.runtime` 配置面
- [机器平面路径授权归 CapabilityGrant](../../implemented/seam/2026-09-21-machine-path-authorization-belongs-to-capability-grant.md) 同一审批 seam 的机器平面侧