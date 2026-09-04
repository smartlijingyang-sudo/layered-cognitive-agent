# Agent Note: 事件 yaml publisher 授权 + trace 装饰性 双向合同

Status: implemented(2026-09-04)

## Problem

2026-09-04 09:30 起 web-standard kernel 启动后所有 HTTP 路由
（`/health`、`/runs`、`/api/device/devices`）统一返回 `500 Internal Server
Error`，但 `lca-ops status` ping 端口仍报 healthy。traceback 唯一异常
`UnauthorizedPublishError: plugin 'ReflectorClass' 未授权 publish
category='spine.transport.route.enter'`。

根因链：

1. `lca_kernel/events/config/observability/spine.yaml` 的 129 处
   `publishers:` token 写的是下划线短形式（`events.spine_reflector_X`），
   而 plugin manifest 的 `id="events.spine.reflector.X"` 是点分形式。
2. `EventRegistry.refresh()` 走 `strict=False`：token miss 静默跳过，
   `publishers[category]` 退化为空 frozenset。
3. webserver `route_register._async_wrapper` 在每个请求进入时同步调
   `emit_transport_route_enter` → `EventBus.publish` 鉴权失败抛
   `UnauthorizedPublishError` → 无任何 handler 兜底 → uvicorn 500。
4. `OwnershipDeclaration.emits` 字段是装饰字段，无代码级对账。

本质问题：publisher 授权 SSOT 加载失败这件事系统不会在 boot 期报告，
observability 副作用进入正确性路径。

## Decision

### 1. `EventRegistry.validate_publisher_authorization()` 后置硬门槛

`refresh()` 之后由调用方显式触发，任一 yaml `publishers` token 既不在
catalog 也非可 import 的 class-path → 抛 `UnknownPluginIdError`（E2/E3
已存在的语义，未新造异常类）。错误信息含 category、token、失败计数。
集中暴露错配，避免 load 阶段某条 token miss 直接打断后续解析。

### 2. `EventRegistry.check_manifest_emits_aligned()` 反向校验

`plugin_id` + `OwnershipDeclaration.emits` 元组传入：每条 emit 必须是
已登记 category 且当前 plugin id 在该 category 的 publishers 集合中。
任一未授权 → `AuthMatrixMismatchError`（E3 已存在的语义）。plugin
manifest 的 `emits` 字段从装饰升级为契约。

### 3. `_resolve_tokens` 默认 strict 在 load 路径放宽

`EventRegistry.from_specs` 在 catalog 已注入分支显式传 `strict=False`，
与 `refresh()` 一致。把"硬门槛"完全集中在 `validate_publisher_authorization`，
load 阶段只做"尽可能多解析 + 收集诊断"。

### 4. `route_register._safe_emit` 限定 except 范围

`_async_wrapper` / `_sync_wrapper` 的所有 `emit_transport_route_*` 调用
改为走 `_safe_emit(execution_point, **kwargs)`。失败仅捕获
`lca_kernel.events.errors.EventMechanismError` 族（`UnauthorizedPublishError`
/ `EventNoSinkError` / 等），不裸 `Exception`。失败时 `log.warning` +
递增 `_trace_emit_failures[execution_point]` 计数（模块级 dict，测试 /
监控可通过 `trace_emit_failures()` 读快照），handler 继续返回业务结果。

非 `EventMechanismError` 异常照常上抛，代码 bug（`AttributeError` /
`TypeError` 等）不被吞。

### 5. yaml 129 处 token 短形式 → 点分

`lca_kernel/events/config/observability/spine.yaml` 15 个 unique token
共 129 处下划线短形式改为点分（与 plugin manifest 一致）。同时把
`lca_kernel/events/test_catalog.py` 15 个 catalog key 同步改为点分。

## 影响面

| 文件 | 改动 |
|---|---|
| `lca_kernel/events/registry.py` | `+validate_publisher_authorization` / `+check_manifest_emits_aligned`；`from_specs` 传 `strict=False` |
| `lca/harness/profile/boot.py` | refresh() 后调 validate + check_manifest_emits_aligned；`_collect_marker_catalog` 返回 catalog + emits_by_id 双 tuple |
| `lca/plugins/transport/webserver/route_register.py` | `_safe_emit` + `_trace_emit_failures` + `trace_emit_failures()`；`_instrument_route_handler` 全部 emit 走 `_safe_emit` |
| `lca_kernel/events/config/observability/spine.yaml` | 129 处 publisher token 下划线 → 点分（15 unique） |
| `lca_kernel/events/test_catalog.py` | 15 个 catalog key 下划线 → 点分 |
| `tests/lca_kernel/events/test_registry_authorization_drift.py` | 新建（7 个测试） |
| `tests/transport/test_route_register_trace_is_decorative.py` | 新建（5 个测试） |
| `scripts/check_events_catalog_consistency.py` | 新建（CI 门禁） |

## 失败模式不再有

- yaml token miss → kernel boot 失败，错误信息含 category + token + 计数
- plugin manifest emits 与 yaml 不一致 → kernel boot 失败，错误信息含 missing_publish
- EventBus publish 失败 → 仅 log warning + 计数，handler 仍返回业务结果
- 代码 bug（非 EventMechanismError）→ fail-fast，不被吞

## 删除条件

- `scripts/check_events_catalog_consistency.py` 上 CI 满 14 天无 false positive
- `_trace_emit_failures` dict 后续可由 metrics endpoint 暴露（prometheus_client
  引入时机另行 ADR）
- `_resolve_tokens(..., strict=False)` 默认值在所有 yaml 已锁定为点分后可改回
  `strict=True`（但需先确认无任何 yaml 仍用 class-path 形态）

跟踪：ADR-0181+1 / ADR-0183 PR-7
